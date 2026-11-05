"""MPRIS media player integration backed by dbus-next.


Qt's QDBusAbstractAdaptor does not export runtime ClassInfo in current PySide6
builds, so the MPRIS interfaces are exported directly with dbus-next from a
small dedicated asyncio thread.
"""

# ruff: noqa: F821, F722, UP037


import asyncio
import threading
from collections.abc import Callable
from typing import Any

from dbus_next import RequestNameReply, Variant
from dbus_next.aio import MessageBus
from dbus_next.service import PropertyAccess, ServiceInterface, dbus_property, method
from loguru import logger

from .ipc import PLAYER_NEXT, PLAYER_PREV, PLAYER_TOGGLE, SHOW_MAIN
from .paths import APP_DISPLAY_NAME, APP_NAME
from .player import PlayerState

SERVICE_NAME = "org.mpris.MediaPlayer2.netease_music"
OBJECT_PATH = "/org/mpris/MediaPlayer2"
ROOT_INTERFACE = "org.mpris.MediaPlayer2"
PLAYER_INTERFACE = "org.mpris.MediaPlayer2.Player"
NO_TRACK = "/org/mpris/MediaPlayer2/TrackList/NoTrack"
POLL_SECONDS = 0.2


class MprisRoot(ServiceInterface):
    def __init__(self, send: Callable[[str], None], request_quit: Callable[[], None]) -> None:
        super().__init__(ROOT_INTERFACE)
        self._send = send
        self._request_quit = request_quit

    @method()
    def Raise(self) -> None:
        self._send(SHOW_MAIN)

    @method()
    def Quit(self) -> None:
        self._request_quit()

    @dbus_property(access=PropertyAccess.READ)
    def CanQuit(self) -> "b":
        return True

    @dbus_property(access=PropertyAccess.READ)
    def CanRaise(self) -> "b":
        return True

    @dbus_property(access=PropertyAccess.READ)
    def Identity(self) -> "s":
        return APP_DISPLAY_NAME

    @dbus_property(access=PropertyAccess.READ)
    def DesktopEntry(self) -> "s":
        return APP_NAME

    @dbus_property(access=PropertyAccess.READ)
    def HasTrackList(self) -> "b":
        return False

    @dbus_property(access=PropertyAccess.READ)
    def SupportedUriSchemes(self) -> "as":
        return []

    @dbus_property(access=PropertyAccess.READ)
    def SupportedMimeTypes(self) -> "as":
        return []


class MprisPlayer(ServiceInterface):
    def __init__(
        self,
        get_state: Callable[[], PlayerState],
        send: Callable[[str], None],
    ) -> None:
        super().__init__(PLAYER_INTERFACE)
        self._get_state = get_state
        self._send = send

    def _status(self) -> str:
        state = self._get_state()
        if state.is_empty:
            return "Stopped"
        return "Playing" if state.playing else "Paused"

    def _metadata(self) -> dict[str, Variant]:
        state = self._get_state()
        if state.is_empty:
            return {"mpris:trackid": Variant("o", NO_TRACK)}
        track = state.song_id if state.song_id is not None else 0
        metadata: dict[str, Variant] = {
            "mpris:trackid": Variant("o", f"/org/163music/track/{track}"),
            "xesam:title": Variant("s", state.title),
            "xesam:artist": Variant("as", list(state.artists)),
        }
        if state.album:
            metadata["xesam:album"] = Variant("s", state.album)
        if state.duration > 0:
            metadata["mpris:length"] = Variant("x", int(state.duration * 1_000_000))
        if state.cover:
            metadata["mpris:artUrl"] = Variant("s", state.cover)
        return metadata

    @method()
    def Next(self) -> None:
        self._send(PLAYER_NEXT)

    @method()
    def Previous(self) -> None:
        self._send(PLAYER_PREV)

    @method()
    def Pause(self) -> None:
        if self._get_state().playing:
            self._send(PLAYER_TOGGLE)

    @method()
    def Play(self) -> None:
        if not self._get_state().playing:
            self._send(PLAYER_TOGGLE)

    @method()
    def PlayPause(self) -> None:
        self._send(PLAYER_TOGGLE)

    @method()
    def Stop(self) -> None:
        if self._get_state().playing:
            self._send(PLAYER_TOGGLE)

    @method()
    def Seek(self, offset: "x") -> None:
        logger.debug("MPRIS Seek is not supported: {}", offset)

    @method()
    def SetPosition(self, track_id: "o", position: "x") -> None:
        logger.debug("MPRIS SetPosition is not supported: {} {}", track_id, position)

    @method()
    def OpenUri(self, uri: "s") -> None:
        logger.debug("MPRIS OpenUri is not supported: {}", uri)

    @dbus_property(access=PropertyAccess.READ)
    def PlaybackStatus(self) -> "s":
        return self._status()

    @dbus_property(access=PropertyAccess.READ)
    def LoopStatus(self) -> "s":
        return "None"

    @dbus_property(access=PropertyAccess.READ)
    def Rate(self) -> "d":
        return 1.0

    @dbus_property(access=PropertyAccess.READ)
    def Shuffle(self) -> "b":
        return False

    @dbus_property(access=PropertyAccess.READ)
    def Metadata(self) -> "a{sv}":
        return self._metadata()

    @dbus_property(access=PropertyAccess.READ)
    def Volume(self) -> "d":
        return 1.0

    @dbus_property(access=PropertyAccess.READ)
    def Position(self) -> "x":
        state = self._get_state()
        if state.is_empty:
            return 0
        return int(state.position_at() * 1_000_000)

    @dbus_property(access=PropertyAccess.READ)
    def MinimumRate(self) -> "d":
        return 1.0

    @dbus_property(access=PropertyAccess.READ)
    def MaximumRate(self) -> "d":
        return 1.0

    @dbus_property(access=PropertyAccess.READ)
    def CanGoNext(self) -> "b":
        return True

    @dbus_property(access=PropertyAccess.READ)
    def CanGoPrevious(self) -> "b":
        return True

    @dbus_property(access=PropertyAccess.READ)
    def CanPlay(self) -> "b":
        return True

    @dbus_property(access=PropertyAccess.READ)
    def CanPause(self) -> "b":
        return True

    @dbus_property(access=PropertyAccess.READ)
    def CanSeek(self) -> "b":
        return False

    @dbus_property(access=PropertyAccess.READ)
    def CanControl(self) -> "b":
        return True

    def publish(self) -> None:
        try:
            self.emit_properties_changed(
                {
                    "PlaybackStatus": self._status(),
                    "Metadata": self._metadata(),
                }
            )
        except Exception as error:  # noqa: BLE001
            logger.debug("Could not publish MPRIS state: {}", error)


class MprisService:
    """Own the MPRIS bus name and drive PropertiesChanged from a worker thread."""

    def __init__(
        self,
        send: Callable[[str], None],
        request_quit: Callable[[], None],
        get_state: Callable[[], PlayerState],
    ) -> None:
        self._send = send
        self._request_quit = request_quit
        self._get_state = get_state
        self._root = MprisRoot(send, request_quit)
        self._player = MprisPlayer(get_state, send)
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._bus: MessageBus | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="mpris-service", daemon=True)
        self._thread.start()

    def _run(self) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._main())
        except Exception as error:  # noqa: BLE001
            logger.warning("MPRIS service failed: {}", error)
        finally:
            try:
                loop.close()
            except Exception:  # noqa: BLE001
                pass

    async def _main(self) -> None:
        bus = await MessageBus().connect()
        self._bus = bus
        try:
            bus.export(OBJECT_PATH, self._root)
            bus.export(OBJECT_PATH, self._player)
            reply = await bus.request_name(SERVICE_NAME)
            if reply != RequestNameReply.PRIMARY_OWNER:
                logger.warning("MPRIS name {} is already owned", SERVICE_NAME)
                return
            logger.info("MPRIS service {} registered", SERVICE_NAME)
            last_key: tuple[Any, ...] | None = None
            while not self._stop.is_set():
                state = self._get_state()
                key = (
                    state.title,
                    state.artists,
                    state.song_id,
                    state.duration,
                    state.cover,
                    state.album,
                    state.playing,
                )
                if key != last_key:
                    last_key = key
                    self._player.publish()
                await asyncio.sleep(POLL_SECONDS)
        finally:
            try:
                bus.disconnect()
            except Exception:  # noqa: BLE001
                pass
            self._bus = None

    def stop(self) -> None:
        self._stop.set()
