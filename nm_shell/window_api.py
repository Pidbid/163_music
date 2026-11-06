"""The ``window.pywebview.api`` surface used by the shell chrome."""

from __future__ import annotations

import sys
import threading
import time
import webbrowser
from collections.abc import Callable
from typing import Any
from urllib.parse import urlsplit

import webview
from loguru import logger

from .paths import APP_URL
from .player import PlayerState
from .window_manager import (
    apply_bounds,
    available_geometry,
    current_bounds,
    native_is_maximized,
    on_qt_gui_thread,
    set_page_background,
    start_system_move,
    start_system_resize,
)

MIN_WIDTH = 940
MIN_HEIGHT = 620


def _make_qt_action_bridge(owner: ShellApi) -> Any:
    """Build a QObject whose slots run native window actions on Qt's GUI thread."""
    try:
        from PySide6.QtCore import QObject, Slot
    except ImportError:
        return None

    class _QtWindowActionBridge(QObject):
        def __init__(self, api: ShellApi) -> None:
            super().__init__()
            self._api = api

        @Slot(str, result=bool)
        def start_resize(self, direction: str) -> bool:
            return self._api._qt_start_system_resize(direction)

        @Slot(result=bool)
        def start_move(self) -> bool:
            return self._api._qt_start_system_move()

        @Slot(result=bool)
        def force_show(self) -> bool:
            return self._api._qt_force_show()

        @Slot(result=bool)
        def page_transparent(self) -> bool:
            return self._api._qt_page_transparent()

    return _QtWindowActionBridge(owner)


class ShellApi:
    """Thread-safe bridge between the web page and the shell state."""

    def __init__(
        self,
        *,
        on_player_state: Callable[[PlayerState], None] | None = None,
        on_window_state: Callable[[bool, bool], None] | None = None,
        request_quit: Callable[[], None] | None = None,
        tray_available: bool = True,
    ) -> None:
        self._main: webview.Window | None = None
        self._qt_actions: Any = None
        self._lock = threading.RLock()
        self._state = PlayerState()
        self._on_player_state = on_player_state
        self._on_window_state = on_window_state
        self._request_quit = request_quit
        self._tray_available = tray_available
        self._main_visible = True
        self._main_maximized = False
        self._restore_bounds: tuple[int, int, int, int] | None = None
        self._linux = sys.platform.startswith("linux")

    def bind(self, window: webview.Window) -> None:
        self._main = window
        self._main_visible = True
        if self._linux:
            self._qt_actions = _make_qt_action_bridge(self)

    # ------------------------------------------------------------------ player
    def update_player_state(self, payload: Any) -> dict[str, Any]:
        state = PlayerState.from_payload(payload)
        with self._lock:
            self._state = state
        callback = self._on_player_state
        if callback is not None:
            try:
                callback(state)
            except Exception as error:  # noqa: BLE001 - never break the page bridge
                logger.warning("Player state callback failed: {}", error)
        return {"ok": True, "title": state.title, "playing": state.playing}

    def player_state(self) -> dict[str, Any]:
        with self._lock:
            return self._state.to_payload()

    def player_action(self, action: str) -> bool:
        """Run one of the injected page's player actions."""
        window = self._main
        if window is None:
            return False
        action = str(action)
        try:
            script = f"window.__nmPlayer && window.__nmPlayer.action({action!r})"
            window.evaluate_js(script)
            return True
        except Exception as error:  # noqa: BLE001
            logger.debug("Player action {} failed: {}", action, error)
            return False

    # ------------------------------------------------------------------ windows
    def _notify_window_state(self) -> None:
        callback = self._on_window_state
        if callback is None:
            return
        try:
            callback(self._main_visible, self._main_maximized)
        except Exception as error:  # noqa: BLE001
            logger.debug("Window state callback failed: {}", error)

    def _refresh_js_state(self) -> None:
        window = self._main
        if window is None:
            return
        try:
            window.evaluate_js(
                "window.__nmShellRefreshWindowState && window.__nmShellRefreshWindowState()"
            )
        except Exception as error:  # noqa: BLE001
            logger.debug("Could not refresh window state in the page: {}", error)

    def window_state(self) -> dict[str, Any]:
        maximized = self._main_maximized
        if self._main is not None and native_is_maximized(self._main):
            maximized = True
        return {
            "maximized": bool(maximized),
            "visible": bool(self._main_visible),
            "trayAvailable": bool(self._tray_available),
        }

    def get_window_bounds(self) -> dict[str, int] | None:
        window = self._main
        if window is None:
            return None
        bounds = current_bounds(window)
        if bounds is None:
            return None
        x, y, width, height = bounds
        return {"x": x, "y": y, "width": width, "height": height}

    def prepare_resize(self) -> dict[str, int] | None:
        """Exit maximized state once before an edge-resize drag starts."""
        window = self._main
        if window is None:
            return None
        if self._main_maximized or native_is_maximized(window):
            self._set_maximized(False)
            time.sleep(0.12)
        return self.get_window_bounds()

    def set_window_bounds(self, x: int, y: int, width: int, height: int) -> bool:
        """Resize/move the frameless main window from an HTML resize handle."""
        window = self._main
        if window is None:
            return False
        width = max(MIN_WIDTH, int(width))
        height = max(MIN_HEIGHT, int(height))
        if self._main_maximized or native_is_maximized(window):
            self._set_maximized(False)
            time.sleep(0.08)
        ok = apply_bounds(window, (int(x), int(y), width, height))
        self._main_maximized = False
        self._restore_bounds = None
        self._notify_window_state()
        return ok

    def move_window(self, x: int, y: int) -> bool:
        """Move the frameless window from the HTML drag fallback."""
        window = self._main
        if window is None:
            return False
        try:
            window.gui.move(int(x), int(y), window.uid)
            return True
        except Exception as error:  # noqa: BLE001
            logger.debug("Could not move main window: {}", error)
            return False

    def begin_system_resize(self, direction: str) -> bool:
        """Start a window-manager resize drag from a frameless HTML edge."""
        window = self._main
        if window is None:
            return False
        if self._main_maximized or native_is_maximized(window):
            self._set_maximized(False)
        return self._qt_action("resize", direction)

    def begin_system_move(self) -> bool:
        """Start a window-manager move drag from the frameless title bar."""
        window = self._main
        if window is None:
            return False
        if self._main_maximized or native_is_maximized(window):
            self._set_maximized(False)
        return self._qt_action("move")

    def page_transparent(self) -> bool:
        """Let the desktop show through the rounded window corners."""
        return self._qt_action("page_transparent")

    def _set_maximized(self, maximized: bool) -> None:
        window = self._main
        if window is None:
            return
        native_max = native_is_maximized(window)
        if maximized == (self._main_maximized or native_max):
            return
        if maximized:
            self._restore_bounds = current_bounds(window)
            geometry = available_geometry(window)
            if geometry is None:
                logger.warning("No available screen geometry; leaving window size unchanged")
                return
            self._main_maximized = True
            self._notify_window_state()
            self._refresh_js_state()
            apply_bounds(window, geometry)
        else:
            try:
                window.restore()
            except Exception as error:  # noqa: BLE001
                logger.debug("Could not restore before resizing: {}", error)
            if self._restore_bounds is not None:
                apply_bounds(window, self._restore_bounds)
            self._main_maximized = False
            self._notify_window_state()
            self._refresh_js_state()

    def _qt_window_handle(self) -> Any:
        from .window_manager import window_handle

        window = self._main
        return window_handle(window) if window is not None else None

    def _qt_start_system_resize(self, direction: str) -> bool:
        window = self._main
        if window is None:
            return False
        return start_system_resize(window, direction)

    def _qt_start_system_move(self) -> bool:
        window = self._main
        if window is None:
            return False
        return start_system_move(window)

    def _qt_force_show(self) -> bool:
        """Restore and raise the native window; must run on Qt's GUI thread."""
        window = self._main
        native = getattr(window, "native", None) if window is not None else None
        if native is None:
            return False
        try:
            native.showNormal()
            native.raise_()
            native.activateWindow()
            logger.debug(
                "Native window restored: visible={} minimized={}",
                native.isVisible(),
                native.isMinimized(),
            )
            return True
        except Exception as error:  # noqa: BLE001
            logger.debug("Could not force-show the native window: {}", error)
            return False

    def _qt_page_transparent(self) -> bool:
        return set_page_background(self._main, None)

    def _qt_action(self, name: str, *args: Any) -> bool:
        bridge = self._qt_actions
        if bridge is None:
            if on_qt_gui_thread():
                if name == "resize":
                    return self._qt_start_system_resize(str(args[0]))
                if name == "force_show":
                    return self._qt_force_show()
                if name == "page_transparent":
                    return self._qt_page_transparent()
                return self._qt_start_system_move()
            logger.debug("Native window {} requested before Qt bridge was ready", name)
            return False

        try:
            from PySide6.QtCore import Q_ARG, Q_RETURN_ARG, QMetaObject, Qt, QThread

            if bridge.thread() is QThread.currentThread():
                if name == "resize":
                    return self._qt_start_system_resize(str(args[0]))
                if name == "force_show":
                    return self._qt_force_show()
                if name == "page_transparent":
                    return self._qt_page_transparent()
                return self._qt_start_system_move()
            if name == "resize":
                result = QMetaObject.invokeMethod(
                    bridge,
                    "start_resize",
                    Qt.ConnectionType.BlockingQueuedConnection,
                    Q_RETURN_ARG(bool),
                    Q_ARG(str, str(args[0])),
                )
            elif name == "force_show":
                result = QMetaObject.invokeMethod(
                    bridge,
                    "force_show",
                    Qt.ConnectionType.BlockingQueuedConnection,
                    Q_RETURN_ARG(bool),
                )
            elif name == "page_transparent":
                result = QMetaObject.invokeMethod(
                    bridge,
                    "page_transparent",
                    Qt.ConnectionType.BlockingQueuedConnection,
                    Q_RETURN_ARG(bool),
                )
            else:
                result = QMetaObject.invokeMethod(
                    bridge,
                    "start_move",
                    Qt.ConnectionType.BlockingQueuedConnection,
                    Q_RETURN_ARG(bool),
                )
            return bool(result)
        except Exception as error:  # noqa: BLE001
            logger.debug("Could not dispatch native window {}: {}", name, error)
            return False

    def main_action(self, action: str) -> bool:
        window = self._main
        if window is None:
            return False
        action = str(action)
        try:
            if action == "toggle":
                return self.main_action("hide" if self._main_visible else "show")
            if action == "show":
                try:
                    window.restore()
                except Exception:
                    pass
                window.show()
                self._qt_action("force_show")
                if self._main_maximized:
                    geometry = available_geometry(window)
                    if geometry is not None:
                        apply_bounds(window, geometry)
                self._main_visible = True
                self._refresh_js_state()
            elif action == "hide":
                window.hide()
                self._main_visible = False
            elif action == "close":
                if self._tray_available:
                    window.hide()
                    self._main_visible = False
                else:
                    self.quit_app()
            elif action == "minimize":
                window.minimize()
                self._main_visible = False
            elif action == "maximize":
                self._set_maximized(True)
            elif action == "restore":
                self._set_maximized(False)
            elif action == "toggle_maximize":
                self._set_maximized(not (self._main_maximized or native_is_maximized(window)))
            elif action == "reload":
                return self.reload_main()
            elif action == "quit":
                self.quit_app()
            else:
                logger.warning("Unknown main window action: {}", action)
                return False
            self._notify_window_state()
            return True
        except Exception as error:  # noqa: BLE001
            logger.opt(exception=True).warning("Window action {} failed: {}", action, error)
            return False

    def reload_main(self) -> bool:
        window = self._main
        if window is None:
            return False
        try:
            window.evaluate_js("window.location.reload()")
            return True
        except Exception:
            try:
                window.load_url(APP_URL)
                return True
            except Exception as error:  # noqa: BLE001
                logger.warning("Could not reload the page: {}", error)
                return False

    def set_tray_available(self, available: bool) -> bool:
        self._tray_available = bool(available)
        return self._tray_available

    def open_external(self, url: str = "") -> bool:
        target = str(url or "").strip()
        split = urlsplit(target)
        if split.scheme not in ("http", "https") or not split.netloc:
            return False
        webbrowser.open(target)
        return True

    def quit_app(self) -> bool:
        if self._request_quit is not None:
            self._request_quit()
            return True
        return False

    def log_client_error(self, message: str) -> bool:
        logger.warning("UI error: {}", str(message)[:2000])
        return True
