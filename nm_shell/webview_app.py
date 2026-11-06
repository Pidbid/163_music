"""The GUI process: one frameless web player window."""

from __future__ import annotations

import base64
import os
import queue
import sys
import threading
from typing import Any

# pywebview's Qt backend imports qtpy before the binding is selected. Force
# PySide6 so a missing PyQt5 package cannot be reported instead.
os.environ["QT_API"] = "pyside6"

import webview  # noqa: E402
from loguru import logger

from . import ipc
from .lyrics import LyricsCache
from .paths import APP_DISPLAY_NAME, APP_URL, ensure_data_dirs, icon_path, resource_path, webengine_dir
from .player import PlayerState
from .window_api import MIN_HEIGHT, MIN_WIDTH, ShellApi
from .window_manager import set_page_background

CHROME_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
CHROMIUM_FLAGS = (
    "--disable-background-timer-throttling "
    "--disable-renderer-backgrounding "
    "--disable-backgrounding-occluded-windows"
)
WINDOW_BASE_COLOR = "#f7f9fc"
TRANSPARENT_WINDOW = sys.platform.startswith("linux")


def _set_chromium_flags() -> None:
    current = os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "")
    missing = [flag for flag in CHROMIUM_FLAGS.split() if flag not in current]
    if missing:
        os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = " ".join([current, *missing]).strip()


def build_chrome_script() -> str:
    script = resource_path("ui", "chrome.js").read_text(encoding="utf-8")
    icon_candidates = (
        resource_path("assets", "icon-64.png"),
        resource_path("assets", "icon.png"),
    )
    icon_file = next((candidate for candidate in icon_candidates if candidate.is_file()), None)
    data_uri = ""
    if icon_file is not None:
        encoded = base64.b64encode(icon_file.read_bytes()).decode("ascii")
        data_uri = f"data:image/png;base64,{encoded}"
    rounded = "true" if TRANSPARENT_WINDOW else "false"
    return script.replace("__NM_ICON_DATA_URI__", data_uri).replace(
        "__NM_ROUNDED_WINDOW__", rounded
    )


def run_webview_process(config: dict[str, Any], commands: Any, state_queue: Any = None) -> int:
    ensure_data_dirs()
    _set_chromium_flags()
    webview.settings["ALLOW_DOWNLOADS"] = False
    webview.settings["ALLOW_FILE_URLS"] = True
    webview.settings["OPEN_EXTERNAL_LINKS_IN_BROWSER"] = True
    webview.settings["SHOW_DEFAULT_MENUS"] = False
    webview.settings["OPEN_DEVTOOLS_IN_DEBUG"] = False
    if config.get("debug"):
        webview.settings["REMOTE_DEBUGGING_PORT"] = int(config.get("debug_port", 9229))

    quit_event = threading.Event()
    tray_state = {"available": True}
    lyrics_cache = LyricsCache()
    lyrics_lock = threading.Lock()
    lyrics_fetching: set[int] = set()
    lyrics_sent: set[int] = set()
    chrome_script: str | None = None

    def put_state(kind: str, *payload: Any) -> None:
        if state_queue is None:
            return
        try:
            state_queue.put_nowait((kind, *payload))
        except Exception as error:  # noqa: BLE001 - the tray may be gone
            logger.debug("Could not publish {} to tray: {}", kind, error)

    def request_lyrics(song_id: int) -> None:
        with lyrics_lock:
            if song_id in lyrics_sent or song_id in lyrics_fetching:
                return
            lyrics_fetching.add(song_id)

        def work() -> None:
            try:
                lines = lyrics_cache.get(song_id)
            except Exception as error:  # noqa: BLE001
                logger.debug("Could not fetch lyrics for {}: {}", song_id, error)
                lines = []
            finally:
                with lyrics_lock:
                    lyrics_fetching.discard(song_id)
            with lyrics_lock:
                lyrics_sent.add(song_id)
            logger.debug("Lyrics fetched for {}: {} lines", song_id, len(lines))
            put_state(ipc.LYRICS, song_id, lines)

        threading.Thread(target=work, name=f"lyrics-{song_id}", daemon=True).start()

    def on_player_state(state: PlayerState) -> None:
        if state_queue is None:
            return
        put_state(ipc.PLAYER_STATE, state.to_payload())
        if state.song_id is not None and state.song_id > 0:
            request_lyrics(state.song_id)

    def on_window_state(visible: bool, maximized: bool) -> None:
        put_state(ipc.WINDOW_STATE, bool(visible), bool(maximized))

    def request_quit() -> None:
        try:
            commands.put(ipc.QUIT)
        except Exception as error:  # noqa: BLE001
            logger.warning("Could not request quit: {}", error)

    api = ShellApi(
        on_player_state=on_player_state,
        on_window_state=on_window_state,
        request_quit=request_quit,
    )

    main = webview.create_window(
        APP_DISPLAY_NAME,
        url=config.get("url") or APP_URL,
        js_api=api,
        width=1380,
        height=880,
        min_size=(MIN_WIDTH, MIN_HEIGHT),
        frameless=True,
        easy_drag=False,
        resizable=True,
        text_select=True,
        zoomable=False,
        transparent=TRANSPARENT_WINDOW,
        shadow=True,
        background_color=WINDOW_BASE_COLOR,
        confirm_close=False,
    )
    api.bind(main)

    if TRANSPARENT_WINDOW:
        def prepare_transparent_window() -> None:
            set_page_background(main, WINDOW_BASE_COLOR)

        main.events.before_show += prepare_transparent_window

    def inject_chrome() -> None:
        nonlocal chrome_script
        try:
            if chrome_script is None:
                chrome_script = build_chrome_script()
            main.run_js(chrome_script)
            if TRANSPARENT_WINDOW:
                threading.Timer(0.15, api.page_transparent).start()
        except Exception as error:  # noqa: BLE001
            logger.warning("Could not inject shell chrome: {}", error)

    def on_loaded() -> None:
        threading.Timer(0.2, inject_chrome).start()

    def main_closing() -> bool:
        if quit_event.is_set():
            return True
        if not tray_state["available"]:
            quit_event.set()
            return True
        api.main_action("hide")
        logger.debug("Main window hidden to tray")
        return False

    main.events.loaded += on_loaded
    main.events.closing += main_closing

    def command_loop() -> None:
        while not quit_event.is_set():
            try:
                command = commands.get(timeout=0.25)
            except (queue.Empty, EOFError, OSError):
                continue
            if command is None:
                continue
            logger.debug("Webview command: {}", command)
            try:
                if command == ipc.SHOW_MAIN:
                    api.main_action("show")
                elif command == ipc.HIDE_MAIN:
                    api.main_action("hide")
                elif command == ipc.TOGGLE_MAIN:
                    api.main_action("toggle")
                elif command == ipc.PLAYER_PREV:
                    api.player_action("prev")
                elif command == ipc.PLAYER_NEXT:
                    api.player_action("next")
                elif command == ipc.PLAYER_TOGGLE:
                    api.player_action("toggle")
                elif command == ipc.RELOAD:
                    api.reload_main()
                elif command == ipc.TRAY_UNAVAILABLE:
                    tray_state["available"] = False
                    api.set_tray_available(False)
                    logger.info("Tray unavailable; close buttons now quit the application")
                elif command == ipc.QUIT:
                    quit_event.set()
                    logger.info("Shutting down webview")
                    try:
                        main.destroy()
                    except Exception as error:  # noqa: BLE001
                        logger.warning("Could not destroy main window: {}", error)
                    threading.Timer(1.5, os._exit, args=(0,)).start()
                    break
                else:
                    logger.warning("Unknown webview command: {}", command)
            except Exception as error:  # noqa: BLE001
                logger.warning("Command {} failed: {}", command, error)

    threading.Thread(target=command_loop, name="webview-commands", daemon=True).start()

    try:
        webview.start(
            gui="qt",
            debug=bool(config.get("debug")),
            private_mode=False,
            storage_path=str(webengine_dir()),
            user_agent=CHROME_UA,
            icon=str(icon_path()),
            http_server=False,
        )
    except Exception:
        logger.exception("Webview failed")
        return 1
    logger.info("Webview process exiting")
    return 0
