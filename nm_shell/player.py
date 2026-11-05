"""Normalized playback state shared by the web page bridge, tray and MPRIS."""

from __future__ import annotations

import math
import time
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

MAX_TITLE = 300
MAX_ALBUM = 200
MAX_ARTISTS = 4
MAX_ARTIST = 100


def _text(value: Any, limit: int) -> str:
    if value is None or isinstance(value, (dict, list, tuple, set)):
        return ""
    return str(value).strip()[:limit]


def _finite_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
    elif isinstance(value, str):
        try:
            number = float(value.strip())
        except ValueError:
            return None
    else:
        return None
    return number if math.isfinite(number) else None


def _seconds(value: Any, *, upper: float = 86400.0) -> float:
    number = _finite_number(value)
    if number is None or number < 0 or number > upper:
        return 0.0
    return number


def _flag(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _song_id(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    text = str(value).strip() if value is not None else ""
    if not text.isdigit():
        return None
    number = int(text)
    return number if number > 0 else None


def _cover(value: Any) -> str:
    text = _text(value, 2000)
    if not text:
        return ""
    split = urlsplit(text)
    if split.scheme not in ("http", "https") or not split.netloc:
        return ""
    return text


def parse_clock(value: str | None) -> float | None:
    """Parse the footer clock (``mm:ss`` or ``h:mm:ss``) into seconds."""
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    parts = [part.strip() for part in text.split(":")]
    if len(parts) not in (2, 3) or any(not part.isdigit() for part in parts):
        return None
    numbers = [int(part) for part in parts]
    if len(numbers) == 2:
        minutes, seconds = numbers
        if seconds >= 60:
            return None
        return float(minutes * 60 + seconds)
    hours, minutes, seconds = numbers
    if minutes >= 60 or seconds >= 60:
        return None
    return float(hours * 3600 + minutes * 60 + seconds)


def parse_percent(value: Any) -> float | None:
    """Parse a CSS progress value such as ``74.50%`` and clamp to 0..100."""
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        return None
    text = str(value).strip()
    if text.endswith("%"):
        text = text[:-1].strip()
    if not text:
        return None
    try:
        number = float(text)
    except ValueError:
        return None
    if not math.isfinite(number) or number < 0 or number > 100:
        return None
    return number


@dataclass(frozen=True)
class PlayerState:
    """A small, validated snapshot of the page's player."""

    title: str = ""
    artists: tuple[str, ...] = ()
    album: str = ""
    song_id: int | None = None
    duration: float = 0.0
    position: float = 0.0
    playing: bool = False
    cover: str = ""
    updated_at: float = 0.0

    @classmethod
    def from_payload(cls, payload: Any, *, now: float | None = None) -> PlayerState:
        if not isinstance(payload, Mapping):
            return cls(updated_at=time.monotonic() if now is None else now)
        raw_artists = payload.get("artists")
        artists: tuple[str, ...] = ()
        if isinstance(raw_artists, (list, tuple)):
            cleaned = [
                _text(artist, MAX_ARTIST) for artist in raw_artists[:MAX_ARTISTS]
            ]
            artists = tuple(artist for artist in cleaned if artist)
        duration = _seconds(payload.get("duration"))
        position = _seconds(payload.get("position"))
        if duration > 0:
            position = min(position, duration)
        return cls(
            title=_text(payload.get("title"), MAX_TITLE),
            artists=artists,
            album=_text(payload.get("album"), MAX_ALBUM),
            song_id=_song_id(payload.get("song_id")),
            duration=duration,
            position=position,
            playing=_flag(payload.get("playing")),
            cover=_cover(payload.get("cover")),
            updated_at=time.monotonic() if now is None else now,
        )

    @property
    def is_empty(self) -> bool:
        return not self.title and self.song_id is None

    @property
    def artist_text(self) -> str:
        return " / ".join(self.artists)

    @property
    def display_label(self) -> str:
        if self.is_empty:
            return "未在播放"
        if self.artists:
            return f"{self.title} - {self.artist_text}"
        return self.title

    def position_at(self, now: float | None = None) -> float:
        """Estimate the current position, advancing while playing."""
        if not self.playing or self.duration <= 0:
            return self.position
        current = time.monotonic() if now is None else now
        elapsed = max(0.0, current - self.updated_at)
        return min(self.duration, self.position + elapsed)

    def to_payload(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "artists": list(self.artists),
            "album": self.album,
            "song_id": self.song_id,
            "duration": self.duration,
            "position": self.position,
            "playing": self.playing,
            "cover": self.cover,
        }
