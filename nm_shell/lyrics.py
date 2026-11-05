"""LRC parsing, lookup and the public NetEase lyric endpoint."""

from __future__ import annotations

import bisect
import html
import json
import logging
import math
import re
import threading
import urllib.request
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

_TIME_TAG = re.compile(r"\[(\d{1,3}):(\d{1,2})(?:[.:](\d{1,3}))?\]")
_OFFSET_TAG = re.compile(r"\[offset:\s*(-?\d+)\s*\]", re.IGNORECASE)
_LYRIC_URL = "https://music.163.com/api/song/lyric?id={song_id}&lv=-1&kv=-1&tv=-1"
_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)


@dataclass(frozen=True, order=True)
class LyricLine:
    time: float
    text: str


def _tag_seconds(minute: str, second: str, fraction: str | None) -> float | None:
    minutes = int(minute)
    seconds = int(second)
    if seconds >= 60:
        return None
    if fraction is None:
        millis = 0
    else:
        millis = int(fraction.ljust(3, "0")[:3])
    return minutes * 60 + seconds + millis / 1000.0


def parse_lrc(text: str | None) -> list[LyricLine]:
    """Parse LRC text, including multiple timestamps and the ``offset`` tag."""
    if not isinstance(text, str) or not text:
        return []
    offset = 0.0
    offset_match = _OFFSET_TAG.search(text)
    if offset_match is not None:
        try:
            offset = int(offset_match.group(1)) / 1000.0
        except ValueError:
            offset = 0.0

    lines: list[LyricLine] = []
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    for raw in normalized.split("\n"):
        tags = list(_TIME_TAG.finditer(raw))
        if not tags:
            continue
        lyric = html.unescape(raw[tags[-1].end() :].strip())
        if not lyric:
            continue
        for tag in tags:
            seconds = _tag_seconds(tag.group(1), tag.group(2), tag.group(3))
            if seconds is None:
                continue
            seconds += offset
            if seconds >= 0:
                lines.append(LyricLine(round(seconds, 3), lyric))

    lines.sort(key=lambda line: (line.time, line.text))
    deduped: list[LyricLine] = []
    for line in lines:
        if not deduped or deduped[-1] != line:
            deduped.append(line)
    return deduped


def parse_lyrics_payload(payload: Any) -> list[LyricLine]:
    """Extract LRC lines from the lyric endpoint's JSON shape."""
    if not isinstance(payload, dict):
        return []
    lrc = payload.get("lrc")
    if not isinstance(lrc, dict):
        return []
    return parse_lrc(lrc.get("lyric"))


def active_index(lines: list[LyricLine], position: float) -> int:
    """Index of the line in effect at ``position``, or -1 before the first line."""
    if not lines or not isinstance(position, (int, float)) or not math.isfinite(position):
        return -1
    times = [line.time for line in lines]
    return bisect.bisect_right(times, float(position)) - 1


def active_line(lines: list[LyricLine], position: float) -> LyricLine | None:
    index = active_index(lines, position)
    return lines[index] if index >= 0 else None


def display_pair(lines: list[LyricLine], position: float) -> tuple[str, str]:
    """Return the current and next lyric lines for the desktop overlay."""
    index = active_index(lines, position)
    current = lines[index].text if index >= 0 else ""
    following = lines[index + 1].text if 0 <= index + 1 < len(lines) else ""
    return current, following


def fetch_lyrics(song_id: int) -> list[LyricLine]:
    """Fetch public LRC lyrics for a song id; returns ``[]`` on any failure."""
    if not isinstance(song_id, int) or song_id <= 0:
        return []
    request = urllib.request.Request(
        _LYRIC_URL.format(song_id=song_id),
        headers={"User-Agent": _USER_AGENT, "Referer": "https://music.163.com/"},
    )
    try:
        with urllib.request.urlopen(request, timeout=8.0) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception as error:  # noqa: BLE001 - network boundary
        logger.debug("Lyrics request failed for %s: %s", song_id, error)
        return []
    return parse_lyrics_payload(payload)


class LyricsCache:
    """Small thread-safe LRU cache of fetched lyric lines."""

    def __init__(self, capacity: int = 64) -> None:
        if capacity < 1:
            raise ValueError("capacity must be positive")
        self._capacity = capacity
        self._items: OrderedDict[int, list[LyricLine]] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, song_id: int) -> list[LyricLine]:
        with self._lock:
            cached = self._items.get(song_id)
            if cached is not None:
                self._items.move_to_end(song_id)
                return cached
        lines = fetch_lyrics(song_id)
        with self._lock:
            self._items[song_id] = lines
            self._items.move_to_end(song_id)
            while len(self._items) > self._capacity:
                self._items.popitem(last=False)
        return lines

    def clear(self) -> None:
        with self._lock:
            self._items.clear()
