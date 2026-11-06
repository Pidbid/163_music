#!/usr/bin/env python3
"""163-music - an unofficial frameless NetEase Cloud Music web player."""

from __future__ import annotations

import argparse
import json
import multiprocessing
import os
import queue
import sys
import threading
import urllib.request
from typing import Any

from loguru import logger

from nm_shell.ipc import (
    HIDE_MAIN,
    QUIT,
    SHOW_MAIN,
    TOGGLE_MAIN,
    TRAY_UNAVAILABLE,
)
from nm_shell.logging_setup import setup_logging
from nm_shell.lyrics import LyricLine, parse_lrc
from nm_shell.paths import APP_DISPLAY_NAME, APP_NAME, APP_URL, icon_path, resource_path
from nm_shell.player import PlayerState
from nm_shell.single_instance import SingleInstance
from nm_shell.tray import TrayHost
from nm_shell.version import __version__


def _is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False) or "__compiled__" in globals())


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="163-music",
        description="非官方网易云音乐网页版 Ubuntu 桌面封装",
    )
    parser.add_argument("--url", default=APP_URL, help="web player URL")
    parser.add_argument("--no-tray", action="store_true", help="run without a tray icon")
    parser.add_argument("--debug", action="store_true", help="verbose logs and remote debugging")
    parser.add_argument("--smoke-test", action="store_true", help="check imports and bundled assets")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser.parse_args(argv)


def _config_from_args(args: argparse.Namespace) -> dict[str, Any]:
    return {"url": args.url, "debug": args.debug}


def _webview_child(config: dict[str, Any], commands: Any, state_queue: Any) -> None:
    setup_logging(
        bool(config.get("debug", False)),
        console=bool(config.get("debug", False)) or not _is_frozen(),
    )
    from nm_shell.webview_app import run_webview_process

    try:
        code = run_webview_process(config, commands, state_queue)
    except Exception:
        logger.exception("Webview process crashed")
        raise
    if code:
        raise SystemExit(code)


def run_smoke(config: dict[str, Any]) -> int:
    setup_logging(bool(config.get("debug", False)), console=True)
    checks: dict[str, Any] = {}
    try:
        os.environ["QT_API"] = "pyside6"
        import dbus_next  # noqa: F401
        import PySide6
        import webview  # noqa: F401

        backend = "unknown"
        if sys.platform.startswith("linux"):
            from qtpy import QtCore, QtGui, QtNetwork, QtWidgets  # noqa: F401, I001
            import webview.platforms.qt  # noqa: F401
            from PySide6 import QtWebEngineCore  # noqa: F401

            backend = "qt-webengine"
        elif sys.platform == "win32":
            import webview.platforms.winforms  # noqa: F401

            backend = "winforms"
        elif sys.platform == "darwin":
            import webview.platforms.cocoa  # noqa: F401

            backend = "cocoa"
        checks["imports"] = {
            "webview": True,
            "pyside6": PySide6.__version__,
            "backend": backend,
            "dbus_next": True,
        }
    except Exception as error:  # noqa: BLE001
        checks["imports"] = {"error": str(error)}

    try:
        from nm_shell.webview_app import build_chrome_script

        script = build_chrome_script()
        checks["chrome"] = {"ok": "__NM_ICON_DATA_URI__" not in script and "nm-shell-bar" in script}
    except Exception as error:  # noqa: BLE001
        checks["chrome"] = {"ok": False, "error": str(error)}

    checks["assets"] = {
        "icon": icon_path().is_file(),
        "chrome": resource_path("ui", "chrome.js").is_file(),
    }
    checks["lyrics"] = parse_lrc("[00:01.00]x") == [LyricLine(1.0, "x")]
    checks["player"] = PlayerState.from_payload({"title": "x"}).title == "x"

    try:
        request = urllib.request.Request(
            APP_URL,
            headers={"User-Agent": "Mozilla/5.0"},
            method="HEAD",
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            checks["network"] = {"online": 200 <= response.status < 500, "status": response.status}
    except Exception as error:  # noqa: BLE001
        checks["network"] = {"online": False, "error": str(error)}

    payload = {
        "ok": bool(
            checks["imports"].get("webview")
            and checks["assets"]["icon"]
            and checks["assets"]["chrome"]
            and checks["lyrics"]
            and checks["player"]
        ),
        "app": APP_NAME,
        "displayName": APP_DISPLAY_NAME,
        "version": __version__,
        "checks": checks,
    }
    print(json.dumps(payload, ensure_ascii=True, indent=2))
    return 0 if payload["ok"] else 1


def _start_tray(config: dict[str, Any], instance: SingleInstance) -> int:
    ctx = multiprocessing.get_context("spawn")
    commands = ctx.Queue()
    state_queue = ctx.Queue()
    child_lock = threading.Lock()
    child: multiprocessing.Process | None = None
    quitting = threading.Event()

    def start_child() -> multiprocessing.Process:
        process = ctx.Process(
            target=_webview_child,
            args=(config, commands, state_queue),
            name="163-music-webview",
            daemon=False,
        )
        process.start()
        logger.info("Started webview child pid={}", process.pid)
        return process

    def ensure_child() -> None:
        nonlocal child
        with child_lock:
            if child is None or not child.is_alive():
                child = start_child()

    def send(command: str) -> None:
        try:
            commands.put(command)
        except Exception as error:  # noqa: BLE001
            logger.warning("Could not send {} to webview child: {}", command, error)

    def on_quit() -> None:
        quitting.set()

    def hard_exit() -> None:
        logger.info("Force exiting tray host")
        os._exit(0)

    ensure_child()
    assert child is not None

    tray = TrayHost(
        send,
        on_quit=on_quit,
        ensure_child=ensure_child,
        state_queue=state_queue,
    )

    def instance_command(command: str) -> None:
        mapping = {
            "show": SHOW_MAIN,
            "hide": HIDE_MAIN,
            "toggle": TOGGLE_MAIN,
            "quit": QUIT,
        }
        send(mapping.get(command, SHOW_MAIN))

    instance.start_server(instance_command)

    def monitor() -> None:
        process = child
        if process is None:
            return
        process.join()
        if quitting.is_set():
            return
        logger.warning("Webview child exited unexpectedly (code={})", process.exitcode)
        tray.stop()
        threading.Timer(2.0, hard_exit).start()

    threading.Thread(target=monitor, name="webview-monitor", daemon=True).start()

    tray_ok = tray.run()
    logger.info("Tray loop ended (started={})", tray_ok)
    quitting.set()
    if not tray_ok:
        logger.warning("No system tray available; the window remains usable without tray controls")
        send(TRAY_UNAVAILABLE)
        with child_lock:
            process = child
        if process is not None:
            process.join()
    else:
        send(QUIT)
        with child_lock:
            process = child
        if process is not None:
            process.join(timeout=10)
            if process.is_alive():
                logger.warning("Webview child did not exit; terminating")
                process.terminate()
                process.join(timeout=5)
    for command_queue in (commands, state_queue):
        try:
            command_queue.close()
        except Exception:  # noqa: BLE001
            pass
    return 0


def _run_direct(config: dict[str, Any], instance: SingleInstance) -> int:
    commands: queue.Queue[str] = queue.Queue()
    commands.put(TRAY_UNAVAILABLE)

    def instance_command(command: str) -> None:
        mapping = {"show": SHOW_MAIN, "hide": HIDE_MAIN, "toggle": TOGGLE_MAIN, "quit": QUIT}
        commands.put(mapping.get(command, SHOW_MAIN))

    instance.start_server(instance_command)
    from nm_shell.webview_app import run_webview_process

    try:
        return run_webview_process(config, commands, None)
    finally:
        instance.close()


def main(argv: list[str] | None = None) -> int:
    multiprocessing.freeze_support()
    args = parse_args(argv)
    config = _config_from_args(args)
    setup_logging(args.debug, console=args.debug or not _is_frozen())
    logger.info("{} v{} starting (pid={})", APP_NAME, __version__, os.getpid())

    if args.smoke_test:
        return run_smoke(config)

    instance = SingleInstance()
    if not instance.acquire():
        logger.info("Another 163-music instance is running")
        if instance.notify_primary("show"):
            return 0
        logger.warning("Primary instance did not answer")
        return 2

    try:
        if args.no_tray:
            return _run_direct(config, instance)
        return _start_tray(config, instance)
    finally:
        instance.close()
        logger.info("{} stopped", APP_NAME)


if __name__ == "__main__":
    sys.exit(main())
