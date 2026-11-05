"""System tray, MPRIS integration and the desktop lyric overlay."""

from __future__ import annotations

import queue
import threading
import time
from collections.abc import Callable
from typing import Any

from loguru import logger

from .ipc import (
    HIDE_MAIN,
    LYRICS,
    PLAYER_NEXT,
    PLAYER_PREV,
    PLAYER_STATE,
    PLAYER_TOGGLE,
    QUIT,
    SHOW_MAIN,
    WINDOW_STATE,
)
from .lyrics import LyricLine, display_pair
from .mpris import MprisService
from .paths import APP_DISPLAY_NAME, APP_NAME, config_dir, icon_path
from .player import PlayerState

POLL_INTERVAL_MS = 150
SHORT_TITLE_LIMIT = 8


def short_title(state: PlayerState) -> str:
    """Tray menu label: only the song title, kept short to avoid a wide menu."""
    if state.is_empty:
        return "未在播放"
    title = state.title.strip()
    if not title:
        return "未在播放"
    if len(title) > SHORT_TITLE_LIMIT:
        return title[: SHORT_TITLE_LIMIT - 1] + "…"
    return title


def _setting_bool(settings: Any, key: str, default: bool) -> bool:
    value = settings.value(key, "true" if default else "false")
    if isinstance(value, bool):
        return value
    return str(value).lower() in {"1", "true", "yes", "on"}


def _lyrics_icon(kind: str) -> Any:
    """Draw the small monochrome icons used by the lyric hover bar."""
    from PySide6.QtCore import QPointF, QRectF, Qt
    from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap, QPolygonF

    pixmap = QPixmap(32, 32)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    try:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.scale(2.0, 2.0)
        white = QColor(255, 255, 255, 236)
        painter.setPen(
            QPen(
                white,
                1.6,
                Qt.PenStyle.SolidLine,
                Qt.PenCapStyle.RoundCap,
                Qt.PenJoinStyle.RoundJoin,
            )
        )
        painter.setBrush(Qt.BrushStyle.NoBrush)
        if kind == "prev":
            painter.setBrush(white)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawPolygon(QPolygonF([QPointF(11, 4), QPointF(6, 8), QPointF(11, 12)]))
            painter.drawRoundedRect(QRectF(4.2, 4, 1.6, 8), 0.6, 0.6)
        elif kind == "next":
            painter.setBrush(white)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawPolygon(QPolygonF([QPointF(5, 4), QPointF(10, 8), QPointF(5, 12)]))
            painter.drawRoundedRect(QRectF(10.2, 4, 1.6, 8), 0.6, 0.6)
        elif kind == "play":
            painter.setBrush(white)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawPolygon(
                QPolygonF([QPointF(5.4, 3.8), QPointF(12.2, 8), QPointF(5.4, 12.2)])
            )
        elif kind == "pause":
            painter.setBrush(white)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(QRectF(5.0, 4, 2.2, 8), 0.7, 0.7)
            painter.drawRoundedRect(QRectF(8.8, 4, 2.2, 8), 0.7, 0.7)
        elif kind == "lock":
            painter.drawRoundedRect(QRectF(5, 8, 6, 5), 1.0, 1.0)
            painter.drawArc(QRectF(5.9, 4.2, 4.2, 5.4), 0, 180 * 16)
            painter.setBrush(white)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(QPointF(8, 10.5), 0.8, 0.8)
        elif kind == "top":
            painter.drawLine(QPointF(4, 4.2), QPointF(12, 4.2))
            painter.drawLine(QPointF(8, 12.2), QPointF(8, 6.4))
            painter.drawLine(QPointF(5.8, 8.6), QPointF(8, 6.4))
            painter.drawLine(QPointF(10.2, 8.6), QPointF(8, 6.4))
    finally:
        painter.end()
    return QIcon(pixmap)


class LyricsWindow:
    """Frameless lyric overlay with hover playback and pin controls."""

    def __init__(
        self,
        settings: Any,
        *,
        on_prev: Callable[[], None],
        on_next: Callable[[], None],
        on_toggle_play: Callable[[], None],
    ) -> None:
        from PySide6.QtCore import QPoint, QSize, Qt, QTimer
        from PySide6.QtGui import QColor, QFont, QPainter, QPen
        from PySide6.QtWidgets import (
            QFrame,
            QGraphicsDropShadowEffect,
            QHBoxLayout,
            QLabel,
            QToolButton,
            QVBoxLayout,
            QWidget,
        )

        initial_locked = _setting_bool(settings, "lyrics/locked", False)
        initial_on_top = _setting_bool(settings, "lyrics/on_top", True)

        class _Window(QWidget):
            def __init__(self) -> None:
                flags = (
                    Qt.WindowType.Tool
                    | Qt.WindowType.FramelessWindowHint
                    | Qt.WindowType.WindowDoesNotAcceptFocus
                )
                if initial_on_top:
                    flags |= Qt.WindowType.WindowStaysOnTopHint
                super().__init__(None, flags)
                self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
                self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
                self.setWindowTitle("桌面歌词")
                self._settings = settings
                self._position_locked = initial_locked
                self._on_top = initial_on_top
                self._playing = False
                self._manual_offset: QPoint | None = None
                self._save_timer = QTimer(self)
                self._save_timer.setInterval(500)
                self._save_timer.setSingleShot(True)
                self._save_timer.timeout.connect(self._save_position)

                layout = QVBoxLayout(self)
                layout.setContentsMargins(28, 16, 28, 46)
                layout.setSpacing(5)
                self.current = QLabel("")
                self.following = QLabel("")
                self.current.setAlignment(Qt.AlignmentFlag.AlignCenter)
                self.following.setAlignment(Qt.AlignmentFlag.AlignCenter)
                self.current.setWordWrap(True)
                self.following.setWordWrap(True)
                self.current.setMaximumWidth(900)
                self.following.setMaximumWidth(900)
                current_font = QFont("Noto Sans CJK SC")
                current_font.setPixelSize(22)
                current_font.setWeight(QFont.Weight.DemiBold)
                self.current.setFont(current_font)
                following_font = QFont("Noto Sans CJK SC")
                following_font.setPixelSize(14)
                following_font.setWeight(QFont.Weight.Medium)
                self.following.setFont(following_font)
                self.current.setStyleSheet("color: #ffffff; background: transparent;")
                self.following.setStyleSheet(
                    "color: rgba(255, 255, 255, 0.66); background: transparent;"
                )
                for label in (self.current, self.following):
                    shadow = QGraphicsDropShadowEffect(self)
                    shadow.setBlurRadius(18)
                    shadow.setOffset(0, 2)
                    shadow.setColor(QColor(0, 0, 0, 190))
                    label.setGraphicsEffect(shadow)
                layout.addWidget(self.current)
                layout.addWidget(self.following)

                self._controls = QFrame(self)
                self._controls.setObjectName("lyricsControls")
                self._controls.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
                self._controls.setStyleSheet(
                    "QFrame#lyricsControls {"
                    " background: rgba(255, 255, 255, 0.075);"
                    " border: 1px solid rgba(255, 255, 255, 0.12);"
                    " border-radius: 13px;"
                    "}"
                    "QToolButton { border: 0; border-radius: 8px; background: transparent; }"
                    "QToolButton:hover { background: rgba(255, 255, 255, 0.14); }"
                    "QToolButton:pressed { background: rgba(255, 255, 255, 0.22); }"
                    "QToolButton:checked { background: rgba(236, 65, 65, 0.78); }"
                )
                controls_layout = QHBoxLayout(self._controls)
                controls_layout.setContentsMargins(5, 4, 5, 4)
                controls_layout.setSpacing(2)

                def add_button(
                    kind: str,
                    tooltip: str,
                    callback: Any = None,
                    *,
                    checkable: bool = False,
                    checked: bool = False,
                ) -> Any:
                    button = QToolButton(self._controls)
                    button.setIcon(_lyrics_icon(kind))
                    button.setIconSize(QSize(16, 16))
                    button.setFixedSize(28, 28)
                    button.setToolTip(tooltip)
                    button.setCursor(Qt.CursorShape.PointingHandCursor)
                    if checkable:
                        button.setCheckable(True)
                        button.setChecked(checked)
                    if callback is not None:
                        button.clicked.connect(callback)
                    controls_layout.addWidget(button)
                    return button

                self._prev_button = add_button("prev", "上一曲", lambda _checked=False: on_prev())
                self._play_button = add_button("play", "播放", lambda _checked=False: on_toggle_play())
                self._next_button = add_button("next", "下一曲", lambda _checked=False: on_next())
                self._lock_button = add_button(
                    "lock",
                    "取消固定" if initial_locked else "固定位置",
                    self._set_locked,
                    checkable=True,
                    checked=initial_locked,
                )
                self._top_button = add_button(
                    "top",
                    "取消置顶" if initial_on_top else "置顶",
                    self._set_on_top,
                    checkable=True,
                    checked=initial_on_top,
                )
                self._controls.hide()
                self._hide_timer = QTimer(self)
                self._hide_timer.setInterval(180)
                self._hide_timer.setSingleShot(True)
                self._hide_timer.timeout.connect(self._maybe_hide_controls)

                self.setMinimumWidth(380)
                self.setMaximumWidth(980)
                self.adjustSize()
                self._place_controls()
                self._restore_position()

            def paintEvent(self, event: Any) -> None:
                painter = QPainter(self)
                try:
                    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
                    painter.setPen(QPen(QColor(255, 255, 255, 24), 1))
                    painter.setBrush(QColor(10, 14, 22, 132))
                    painter.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 16, 16)
                finally:
                    painter.end()

            def resizeEvent(self, event: Any) -> None:
                super().resizeEvent(event)
                self._place_controls()

            def _place_controls(self) -> None:
                self._controls.adjustSize()
                x = (self.width() - self._controls.width()) // 2
                y = self.height() - self._controls.height() - 7
                self._controls.move(max(8, x), max(8, y))

            def enterEvent(self, event: Any) -> None:
                self._hide_timer.stop()
                self._controls.show()
                self._controls.raise_()
                super().enterEvent(event)

            def leaveEvent(self, event: Any) -> None:
                self._hide_timer.start()
                super().leaveEvent(event)

            def _maybe_hide_controls(self) -> None:
                if not self.isVisible() or not (
                    self.underMouse() or self._controls.underMouse()
                ):
                    self._controls.hide()
                    return
                self._controls.show()
                self._controls.raise_()

            def mousePressEvent(self, event: Any) -> None:
                if event.button() != Qt.MouseButton.LeftButton:
                    return super().mousePressEvent(event)
                if self._position_locked:
                    return
                handle = self.windowHandle()
                if handle is not None and handle.startSystemMove():
                    return
                self._manual_offset = (
                    event.globalPosition().toPoint() - self.frameGeometry().topLeft()
                )

            def mouseMoveEvent(self, event: Any) -> None:
                if self._manual_offset is None:
                    return super().mouseMoveEvent(event)
                if event.buttons() & Qt.MouseButton.LeftButton:
                    self.move(event.globalPosition().toPoint() - self._manual_offset)

            def mouseReleaseEvent(self, event: Any) -> None:
                self._manual_offset = None
                self._save_timer.start()
                super().mouseReleaseEvent(event)

            def moveEvent(self, event: Any) -> None:
                self._save_timer.start()
                super().moveEvent(event)

            def _save_position(self) -> None:
                if self.isVisible():
                    self._settings.setValue("lyrics/x", int(self.x()))
                    self._settings.setValue("lyrics/y", int(self.y()))

            def _restore_position(self) -> None:
                try:
                    from PySide6.QtCore import QPoint
                    from PySide6.QtGui import QGuiApplication

                    x = int(self._settings.value("lyrics/x", -1))
                    y = int(self._settings.value("lyrics/y", -1))
                    screens = QGuiApplication.screens()
                    valid = any(
                        screen.availableGeometry().contains(QPoint(x, y)) for screen in screens
                    )
                    if not valid:
                        screen = QGuiApplication.primaryScreen()
                        if screen is not None:
                            area = screen.availableGeometry()
                            x = area.x() + (area.width() - self.width()) // 2
                            y = area.bottom() - self.height() - 96
                    if x >= 0 and y >= 0 and screens:
                        self.move(x, y)
                except Exception as error:  # noqa: BLE001
                    logger.debug("Could not restore lyric window position: {}", error)

            def set_lines(self, current: str, following: str) -> None:
                self.current.setText(current)
                self.following.setText(following)
                self.following.setVisible(bool(following))
                self.adjustSize()
                self._place_controls()
                if current or following:
                    if not self.isVisible():
                        self.show()
                    self.raise_()
                    self._maybe_hide_controls()
                else:
                    self.hide()

            def set_playing(self, playing: bool) -> None:
                if playing == self._playing:
                    return
                self._playing = bool(playing)
                self._play_button.setIcon(_lyrics_icon("pause" if self._playing else "play"))
                self._play_button.setToolTip("暂停" if self._playing else "播放")

            def _set_locked(self, checked: bool) -> None:
                self._position_locked = bool(checked)
                self._settings.setValue("lyrics/locked", self._position_locked)
                self._lock_button.setToolTip(
                    "取消固定" if self._position_locked else "固定位置"
                )

            def _set_on_top(self, checked: bool) -> None:
                self._on_top = bool(checked)
                self._settings.setValue("lyrics/on_top", self._on_top)
                self._top_button.setToolTip("取消置顶" if self._on_top else "置顶")
                self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, self._on_top)
                self.show()
                self.raise_()

        self.widget = _Window()

    def set_lines(self, current: str, following: str) -> None:
        self.widget.set_lines(current, following)

    def set_playing(self, playing: bool) -> None:
        self.widget.set_playing(playing)

    def hide(self) -> None:
        self.widget.hide()

    def show(self) -> None:
        self.widget.show()


class TrayHost:
    """Owns the tray icon, MPRIS service and lyric window."""

    def __init__(
        self,
        send: Callable[[str], None],
        *,
        on_quit: Callable[[], None],
        ensure_child: Callable[[], None] | None = None,
        state_queue: Any = None,
    ) -> None:
        self._send = send
        self._on_quit = on_quit
        self._ensure_child = ensure_child
        self._state_queue = state_queue
        self._qt_app: Any = None
        self._tray: Any = None
        self._menu: Any = None
        self._quit_bridge: Any = None
        self._quit_requested = False
        self._state = PlayerState()
        self._lyrics: list[LyricLine] = []
        self._lyrics_song_id: int | None = None
        self._lyrics_enabled = False
        self._lyrics_shown = False
        self._lyrics_window: LyricsWindow | None = None
        self._settings: Any = None
        self._show_action: Any = None
        self._hide_action: Any = None
        self._song_action: Any = None
        self._play_action: Any = None
        self._lyrics_action: Any = None
        self._visible = True
        self._mpris: Any = None
        self._poll_timer: Any = None
        self._last_activation = 0.0
        self._quit_lock = threading.Lock()

    # ------------------------------------------------------------------ commands
    def _command(self, command: str) -> None:
        if self._ensure_child is not None:
            try:
                self._ensure_child()
            except Exception as error:  # noqa: BLE001
                logger.warning("Could not restart webview child: {}", error)
        try:
            self._send(command)
        except Exception as error:  # noqa: BLE001
            logger.warning("Could not send {} to webview child: {}", command, error)

    def _show(self, icon: Any = None, item: Any = None) -> None:
        self._visible = True
        self._command(SHOW_MAIN)
        self._sync_window_actions()

    def _hide(self, icon: Any = None, item: Any = None) -> None:
        self._visible = False
        self._command(HIDE_MAIN)
        self._sync_window_actions()

    def _toggle_window(self, icon: Any = None, item: Any = None) -> None:
        if self._visible:
            self._hide()
        else:
            self._show()

    def _prev(self, icon: Any = None, item: Any = None) -> None:
        self._command(PLAYER_PREV)

    def _next(self, icon: Any = None, item: Any = None) -> None:
        self._command(PLAYER_NEXT)

    def _toggle_play(self, icon: Any = None, item: Any = None) -> None:
        self._command(PLAYER_TOGGLE)

    def _sync_window_actions(self) -> None:
        if self._show_action is not None:
            self._show_action.setEnabled(not self._visible)
        if self._hide_action is not None:
            self._hide_action.setEnabled(self._visible)

    def _toggle_lyrics(self, checked: bool) -> None:
        self._lyrics_enabled = bool(checked)
        logger.info("Desktop lyrics {}", "enabled" if self._lyrics_enabled else "disabled")
        if self._settings is not None:
            self._settings.setValue("lyrics/enabled", self._lyrics_enabled)
        self._update_lyrics()

    def _quit(self, icon: Any = None, item: Any = None) -> None:
        with self._quit_lock:
            if self._quit_requested:
                return
            self._quit_requested = True
        self._command(QUIT)
        try:
            self._on_quit()
        finally:
            self.stop()

    # ------------------------------------------------------------------ state
    def _drain(self) -> None:
        if self._state_queue is None:
            return
        for _ in range(32):
            try:
                message = self._state_queue.get_nowait()
            except queue.Empty:
                return
            except (EOFError, OSError, ValueError) as error:
                logger.debug("Tray state queue unavailable: {}", error)
                return
            try:
                self._handle_message(message)
            except Exception as error:  # noqa: BLE001
                logger.warning("Could not apply tray state: {}", error)

    def _handle_message(self, message: Any) -> None:
        if not isinstance(message, tuple) or not message:
            return
        kind = message[0]
        if kind == PLAYER_STATE and len(message) >= 2:
            state = PlayerState.from_payload(message[1])
            if state.song_id != self._state.song_id:
                self._lyrics = []
                self._lyrics_song_id = None
            self._state = state
            self._apply_state()
        elif kind == LYRICS and len(message) >= 3:
            song_id = message[1]
            lines = message[2]
            if isinstance(song_id, int) and isinstance(lines, list):
                self._lyrics = [line for line in lines if isinstance(line, LyricLine)]
                self._lyrics_song_id = song_id
                logger.debug("Lyrics received for {}: {} lines", song_id, len(self._lyrics))
                self._update_lyrics()
        elif kind == WINDOW_STATE and len(message) >= 3:
            self._visible = bool(message[1])
            self._sync_window_actions()

    def _apply_state(self) -> None:
        state = self._state
        if self._song_action is not None:
            self._song_action.setText(short_title(state))
        if self._play_action is not None:
            self._play_action.setText("暂停" if state.playing else "播放")
        if self._tray is not None:
            tooltip = APP_DISPLAY_NAME
            if not state.is_empty:
                tooltip = f"{APP_DISPLAY_NAME}\n{state.display_label[:120]}"
            self._tray.setToolTip(tooltip)
        self._update_lyrics()

    def _update_lyrics(self) -> None:
        window = self._lyrics_window
        if window is None:
            return
        if not self._lyrics_enabled or self._lyrics_song_id is None:
            if self._lyrics_shown:
                logger.debug("Desktop lyrics hidden")
                self._lyrics_shown = False
            window.hide()
            return
        state = self._state
        if state.song_id != self._lyrics_song_id or not self._lyrics:
            if self._lyrics_shown:
                logger.debug("Desktop lyrics hidden")
                self._lyrics_shown = False
            window.hide()
            return
        current, following = display_pair(self._lyrics, state.position_at())
        if not self._lyrics_shown:
            logger.debug("Desktop lyrics showing: {!r}", current or following)
            self._lyrics_shown = True
        if not current:
            window.set_lines(following, "")
        else:
            window.set_lines(current, following)

    def stop(self) -> None:
        bridge = self._quit_bridge
        if bridge is None:
            return
        try:
            bridge.requested.emit()
        except Exception as error:  # noqa: BLE001
            logger.debug("Qt tray stop failed: {}", error)

    # ------------------------------------------------------------------ Qt
    def _run_qt(self) -> bool:
        try:
            from PySide6.QtCore import QObject, Qt, QTimer, Signal
            from PySide6.QtGui import QIcon
            from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon
        except Exception as error:  # noqa: BLE001
            logger.warning("Qt tray unavailable: {}", error)
            return False

        app = QApplication.instance() or QApplication([])
        app.setApplicationName(APP_NAME)
        app.setApplicationDisplayName(APP_DISPLAY_NAME)
        app.setDesktopFileName(APP_NAME)
        app.setQuitOnLastWindowClosed(False)
        app.setWindowIcon(QIcon(str(icon_path())))

        if not QSystemTrayIcon.isSystemTrayAvailable():
            logger.warning("System tray is unavailable; close buttons will quit instead of hiding")
            return False

        from PySide6.QtCore import QSettings

        settings = QSettings(str(config_dir() / "settings.ini"), QSettings.Format.IniFormat)
        self._settings = settings
        self._lyrics_enabled = str(settings.value("lyrics/enabled", "false")).lower() in {
            "1",
            "true",
            "yes",
        }
        self._lyrics_window = LyricsWindow(
            settings,
            on_prev=self._prev,
            on_next=self._next,
            on_toggle_play=self._toggle_play,
        )

        class _QuitBridge(QObject):
            requested = Signal()

        bridge = _QuitBridge()
        self._quit_bridge = bridge

        icon = QIcon(str(icon_path()))
        tray = QSystemTrayIcon(icon, app)
        tray.setToolTip(APP_DISPLAY_NAME)
        menu = QMenu()
        self._show_action = menu.addAction("显示窗口")
        self._show_action.triggered.connect(self._show)
        self._hide_action = menu.addAction("隐藏窗口")
        self._hide_action.triggered.connect(self._hide)
        menu.addSeparator()
        self._song_action = menu.addAction("当前播放：未在播放")
        self._song_action.setEnabled(False)
        menu.addSeparator()
        prev_action = menu.addAction("上一曲")
        prev_action.triggered.connect(self._prev)
        self._play_action = menu.addAction("播放")
        self._play_action.triggered.connect(self._toggle_play)
        next_action = menu.addAction("下一曲")
        next_action.triggered.connect(self._next)
        menu.addSeparator()
        self._lyrics_action = menu.addAction("桌面歌词")
        self._lyrics_action.setCheckable(True)
        self._lyrics_action.setChecked(self._lyrics_enabled)
        self._lyrics_action.toggled.connect(self._toggle_lyrics)
        menu.addSeparator()
        quit_action = menu.addAction("退出")
        quit_action.triggered.connect(self._quit)
        tray.setContextMenu(menu)
        self._sync_window_actions()

        def on_activated(reason: Any) -> None:
            if reason not in (
                QSystemTrayIcon.ActivationReason.Trigger,
                QSystemTrayIcon.ActivationReason.DoubleClick,
            ):
                return
            now = time.monotonic()
            if now - self._last_activation < 0.35:
                return
            self._last_activation = now
            self._toggle_window()

        tray.activated.connect(on_activated)

        poll_timer = QTimer()
        poll_timer.setInterval(POLL_INTERVAL_MS)
        poll_timer.timeout.connect(self._drain)
        poll_timer.start()

        def request_shutdown() -> None:
            if poll_timer is not None:
                poll_timer.stop()
            app.quit()

        bridge.requested.connect(request_shutdown, Qt.ConnectionType.QueuedConnection)

        self._qt_app = app
        self._tray = tray
        self._menu = menu
        self._poll_timer = poll_timer
        self._mpris = MprisService(
            send=self._command,
            request_quit=self._quit,
            get_state=lambda: self._state,
        )
        self._mpris.start()
        tray.show()
        self._apply_state()
        logger.info("System tray icon started (Qt)")
        try:
            app.exec()
            return True
        except Exception as error:  # noqa: BLE001
            logger.warning("Qt tray loop failed: {}", error)
            return False
        finally:
            if poll_timer is not None:
                poll_timer.stop()
            if self._mpris is not None:
                self._mpris.stop()
                self._mpris = None
            self._poll_timer = None
            self._quit_bridge = None
            self._qt_app = None
            try:
                tray.hide()
                menu.deleteLater()
            except Exception:  # noqa: BLE001
                pass
            self._tray = None
            self._menu = None
            if self._lyrics_window is not None:
                self._lyrics_window.hide()
                self._lyrics_window = None

    def run(self) -> bool:
        """Run the Qt tray loop; returns False when the desktop has no tray."""
        return self._run_qt()
