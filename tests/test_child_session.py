"""One webview child per session: queues must not outlive their reader."""

from __future__ import annotations

import multiprocessing
import queue
import time

from nm_shell.child_session import ChildSession


def _echo_commands(commands, states) -> None:
    states.put(("ready", None))
    while True:
        command = commands.get()
        states.put(("command", command))
        if command == "stop":
            return


def _session(on_channels=None) -> ChildSession:
    ctx = multiprocessing.get_context("spawn")
    return ChildSession(
        ctx,
        _echo_commands,
        lambda channels: (channels.commands, channels.states),
        name="163-music-test-child",
        on_channels=on_channels,
    )


def _await(queue_, expected, timeout: float = 30.0):
    deadline = time.monotonic() + timeout
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise AssertionError(f"child never reported {expected!r}")
        try:
            message = queue_.get(timeout=min(remaining, 0.5))
        except queue.Empty:
            continue
        if message == expected:
            return


def test_a_woken_child_receives_commands_again() -> None:
    # The tray sleeps the player by terminating a child that is blocked in
    # Queue.get(). Reusing that queue leaves its reader lock held, so the
    # replacement child never receives another command (0.2.0 regression).
    queues = {}
    session = _session(lambda channels: queues.update(states=channels.states))
    try:
        assert session.ensure_running() is True
        _await(queues["states"], ("ready", None))
        time.sleep(0.3)  # the child is now blocked inside get()

        session.retire()

        assert session.ensure_running() is True
        assert session.send("player_next") is True
        _await(queues["states"], ("command", "player_next"))
    finally:
        session.retire()


def test_a_sleeping_session_accepts_no_commands() -> None:
    session = _session()
    try:
        session.retire()
        assert session.send("player_next") is False
        assert session.process is None
    finally:
        session.retire()
