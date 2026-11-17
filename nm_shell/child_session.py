"""The disposable process that hosts the web player.

QtWebEngine's own page lifecycle states free nothing on the Qt build here, so
the tray suspends the player by dropping its process. A multiprocessing queue
cannot outlive the process that reads it: a child terminated inside ``get``
keeps the queue's reader lock, and every later reader blocks in it forever.
Each child therefore gets its own queues, created with the process and closed
with it; a restart never inherits a dead session's endpoints.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any

from loguru import logger


class Channels:
    """The command and state queues that belong to one child process."""

    def __init__(self, ctx: Any) -> None:
        self.commands = ctx.Queue()
        self.states = ctx.Queue()

    def close(self) -> None:
        for endpoint in (self.commands, self.states):
            try:
                endpoint.cancel_join_thread()
                endpoint.close()
            except Exception as error:  # noqa: BLE001 - best-effort cleanup
                logger.debug("Could not close a child queue: {}", error)


class ChildSession:
    """Own one webview child process and the queues that go with it."""

    def __init__(
        self,
        ctx: Any,
        target: Callable[..., None],
        arguments: Callable[[Channels], tuple[Any, ...]],
        *,
        name: str,
        on_channels: Callable[[Channels], None] | None = None,
    ) -> None:
        self._ctx = ctx
        self._target = target
        self._arguments = arguments
        self._name = name
        self._on_channels = on_channels
        self._lock = threading.Lock()
        self._process: Any = None
        self._channels: Channels | None = None

    @property
    def process(self) -> Any:
        return self._process

    def ensure_running(self) -> bool:
        """Start a child with fresh queues when the current one is gone."""
        with self._lock:
            if self._process is not None and self._process.is_alive():
                return False
            channels = Channels(self._ctx)
            process = self._ctx.Process(
                target=self._target,
                args=self._arguments(channels),
                name=self._name,
                daemon=False,
            )
            process.start()
            self._process = process
            self._channels = channels
            notify = self._on_channels
        logger.info("Started webview child pid={}", process.pid)
        if notify is not None:
            try:
                notify(channels)
            except Exception as error:  # noqa: BLE001 - the child is already running
                logger.warning("Could not publish the child queues: {}", error)
        return True

    def send(self, command: str) -> bool:
        """Queue a command for the current child; False when it is not running."""
        with self._lock:
            channels = self._channels
            process = self._process
            if channels is None or process is None or not process.is_alive():
                return False
            try:
                channels.commands.put(command)
            except Exception as error:  # noqa: BLE001
                logger.warning("Could not send {} to the webview child: {}", command, error)
                return False
        return True

    def retire(self, timeout: float = 5.0) -> Any:
        """Stop the child and drop its queues so they are never reused."""
        with self._lock:
            process = self._process
            channels = self._channels
            self._process = None
            self._channels = None
        if process is None:
            return None
        if process.is_alive():
            process.terminate()
            process.join(timeout)
            if process.is_alive():
                logger.warning("Webview child did not exit; killing pid={}", process.pid)
                process.kill()
                process.join(timeout)
        if channels is not None:
            channels.close()
        return process
