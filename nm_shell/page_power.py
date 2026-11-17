"""When the hidden web player may be put to sleep.

QtWebEngine's own page lifecycle states are no-ops on the Qt 6.12 build here
(``setLifecycleState(Frozen)`` is immediately reported as ``Active`` again and
frees nothing), so the only thing that really hands memory back is dropping the
process that hosts the page. The shell already runs that page in its own child
process while it has a tray icon, so "discard the page" is: terminate the child
once the window is hidden and nothing makes sound.

The rules below are what keeps the music alive: a page that is playing, or that
the engine reports as audible, must never be suspended. Audibility comes from
``QWebEnginePage.recentlyAudible()`` rather than the page's own script, so a
player whose state reporting is missing or wrong still keeps its page.

A paused player may sleep; the site restores its current track when the page
comes back, and the command that woke it is replayed once the page is ready
(see ``nm_shell.webview_app``).

Suspension happens once per hiding: after the tray has to wake the player (a
command, or the window being shown) the page stays up until the next hide, so a
sleeping player cannot be put back to sleep right after a play command.
"""

from __future__ import annotations

ACTIVE = "active"
SUSPENDED = "suspended"


def may_suspend(hidden: bool, playing: bool, audible: bool, armed: bool = True) -> bool:
    """A hidden, silent, unarmed-per-hide page may be suspended."""
    return bool(hidden) and bool(armed) and not bool(playing) and not bool(audible)


class SuspendPolicy:
    """Track what the tray knows and answer whether the page may sleep."""

    def __init__(self) -> None:
        self._hidden = False
        self._playing = False
        self._audible = False
        self._armed = False

    @property
    def armed(self) -> bool:
        return self._armed

    def set_hidden(self, hidden: bool) -> None:
        self._hidden = bool(hidden)
        self._armed = bool(hidden)

    def set_playing(self, playing: bool) -> None:
        self._playing = bool(playing)
        if self._playing:
            self._armed = False

    def set_audible(self, audible: bool) -> None:
        self._audible = bool(audible)

    def needs_suspend(self) -> bool:
        return may_suspend(self._hidden, self._playing, self._audible, self._armed)

    def disarm(self) -> None:
        """Called once the page has been put to sleep (or woken by a command)."""
        self._armed = False
