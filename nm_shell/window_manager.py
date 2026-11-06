"""Native Qt helpers for the frameless Linux window."""

from __future__ import annotations

import threading
from typing import Any

from loguru import logger

Bounds = tuple[int, int, int, int]


def on_qt_gui_thread() -> bool:
    """Best-effort check that avoids touching Qt widgets off the GUI thread."""
    try:
        from PySide6.QtCore import QCoreApplication, QThread
    except ImportError:
        return threading.current_thread() is threading.main_thread()
    app = QCoreApplication.instance()
    if app is None:
        return threading.current_thread() is threading.main_thread()
    return QThread.currentThread() is app.thread()


def browser_view(window: Any) -> Any:
    gui = getattr(window, "gui", None)
    instances = getattr(getattr(gui, "BrowserView", None), "instances", {})
    return instances.get(getattr(window, "uid", None))


def set_page_background(window: Any, color: str | None) -> bool:
    """Set the WebEngine page background; ``None`` makes it transparent.

    Must run on Qt's GUI thread. The page background is independent of the
    window palette, so it is the only way to hide the viewport base colour
    while the CSS clip path rounds the corners.
    """
    view = browser_view(window)
    if view is None:
        return False
    try:
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QColor

        page = view.webview.page()
        page.setBackgroundColor(Qt.GlobalColor.transparent if color is None else QColor(color))
        return True
    except Exception as error:  # noqa: BLE001 - Qt raises implementation-specific errors
        logger.debug("Could not set the WebEngine page background: {}", error)
        return False


def window_handle(window: Any) -> Any:
    view = browser_view(window)
    if view is None:
        return None
    try:
        return view.windowHandle()
    except Exception as error:  # noqa: BLE001 - Qt raises implementation-specific errors
        logger.debug("Could not read the Qt window handle: {}", error)
        return None


def current_bounds(window: Any) -> Bounds | None:
    try:
        x, y = window.gui.get_position(window.uid)
        width, height = window.gui.get_size(window.uid)
        if x is None or y is None or width is None or height is None:
            return None
        return (int(x), int(y), int(width), int(height))
    except Exception as error:  # noqa: BLE001
        logger.debug("Could not read window bounds: {}", error)
        return None


def available_geometry(window: Any) -> Bounds | None:
    """Return the work area of the screen holding the window."""
    try:
        from PySide6.QtCore import QPoint
        from PySide6.QtGui import QGuiApplication

        view = browser_view(window)
        screen = None
        if view is not None:
            handle = view.windowHandle()
            if handle is not None:
                screen = handle.screen()
            if screen is None:
                screen = QGuiApplication.screenAt(QPoint(view.x(), view.y()))
        if screen is None:
            screen = QGuiApplication.primaryScreen()
        if screen is None:
            return None
        rect = screen.availableGeometry()
        return (int(rect.x()), int(rect.y()), int(rect.width()), int(rect.height()))
    except Exception as error:  # noqa: BLE001
        logger.debug("Could not read available screen geometry: {}", error)
        return None


def apply_bounds(window: Any, bounds: Bounds) -> bool:
    x, y, width, height = bounds
    try:
        from webview.window import FixPoint

        window.gui.resize(int(width), int(height), window.uid, FixPoint.NORTH | FixPoint.WEST)
        window.gui.move(int(x), int(y), window.uid)
        return True
    except Exception as error:  # noqa: BLE001
        logger.debug("Could not apply window bounds: {}", error)
        return False


def start_system_move(window: Any) -> bool:
    handle = window_handle(window)
    if handle is None:
        return False
    try:
        return bool(handle.startSystemMove())
    except Exception as error:  # noqa: BLE001
        logger.debug("Could not start native window move: {}", error)
        return False


def start_system_resize(window: Any, direction: str) -> bool:
    handle = window_handle(window)
    if handle is None:
        return False
    direction = "".join(char for char in str(direction).lower() if char in "nsew")
    if not direction:
        return False
    try:
        from PySide6.QtCore import Qt

        edges = Qt.Edge(0)
        if "n" in direction:
            edges |= Qt.Edge.TopEdge
        if "s" in direction:
            edges |= Qt.Edge.BottomEdge
        if "w" in direction:
            edges |= Qt.Edge.LeftEdge
        if "e" in direction:
            edges |= Qt.Edge.RightEdge
        return bool(handle.startSystemResize(edges))
    except Exception as error:  # noqa: BLE001
        logger.debug("Could not start native window resize: {}", error)
        return False


def native_is_maximized(window: Any) -> bool:
    native = getattr(window, "native", None)
    try:
        from PySide6.QtCore import Qt

        return bool(native.windowState() & Qt.WindowState.WindowMaximized)
    except Exception:  # noqa: BLE001
        return False
