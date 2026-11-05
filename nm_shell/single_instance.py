"""Single-instance guard with a tiny Unix-domain command socket."""

from __future__ import annotations

import os
import socket
import threading
import time
from collections.abc import Callable
from pathlib import Path

from loguru import logger

from .paths import data_dir, ensure_data_dirs, instance_socket

WINDOWS_INSTANCE_PORT = 47834


class SingleInstance:
    """Become the primary instance, or notify the running one to show itself."""

    def __init__(
        self,
        socket_path: Path | None = None,
        lock_path: Path | None = None,
    ) -> None:
        self.socket_path = Path(socket_path) if socket_path else instance_socket()
        self.lock_path = Path(lock_path) if lock_path else data_dir() / "instance.lock"
        self._lock_handle = None
        self._server: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    def acquire(self) -> bool:
        ensure_data_dirs()
        if os.name == "nt":
            try:
                server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                server.bind(("127.0.0.1", WINDOWS_INSTANCE_PORT))
                server.listen(8)
                server.settimeout(0.5)
            except OSError:
                return False
            self._server = server
            return True
        try:
            self.lock_path.parent.mkdir(parents=True, exist_ok=True)
            self._lock_handle = self.lock_path.open("a+")
        except OSError as error:
            logger.warning("Could not open instance lock: {}", error)
            return True
        try:
            import fcntl

            fcntl.flock(self._lock_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except (ImportError, OSError):
            self._lock_handle.close()
            self._lock_handle = None
            return False

    def notify_primary(self, command: str = "show", timeout: float = 3.0) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                if os.name == "nt":
                    with socket.create_connection(
                        ("127.0.0.1", WINDOWS_INSTANCE_PORT), timeout=0.5
                    ) as client:
                        client.sendall(f"{command}\n".encode())
                        reply = client.recv(16).strip()
                        return reply == b"ok"
                with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
                    client.settimeout(0.5)
                    client.connect(str(self.socket_path))
                    client.sendall(f"{command}\n".encode())
                    reply = client.recv(16).strip()
                    return reply == b"ok"
            except OSError:
                time.sleep(0.15)
        return False

    def start_server(self, callback: Callable[[str], None]) -> bool:
        if os.name == "nt":
            if self._server is None:
                return False
            self._stop.clear()
            self._thread = threading.Thread(
                target=self._serve, args=(callback,), name="instance-server", daemon=True
            )
            self._thread.start()
            return True
        if self._lock_handle is None:
            return False
        self._stop.clear()
        try:
            self.socket_path.parent.mkdir(parents=True, exist_ok=True)
            if self.socket_path.exists():
                self.socket_path.unlink()
            server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            server.bind(str(self.socket_path))
            server.listen(8)
            server.settimeout(0.5)
        except OSError as error:
            logger.warning("Could not start instance socket: {}", error)
            return False
        self._server = server
        self._thread = threading.Thread(target=self._serve, args=(callback,), name="instance-server", daemon=True)
        self._thread.start()
        return True

    def _serve(self, callback: Callable[[str], None]) -> None:
        assert self._server is not None
        while not self._stop.is_set():
            try:
                connection, _ = self._server.accept()
            except TimeoutError:
                continue
            except OSError:
                break
            try:
                with connection:
                    connection.settimeout(1.0)
                    data = connection.recv(64).decode("utf-8", "ignore").strip()
                    if data:
                        callback(data)
                    connection.sendall(b"ok\n")
            except OSError as error:
                logger.debug("Instance command failed: {}", error)

    def close(self) -> None:
        self._stop.set()
        server = self._server
        self._server = None
        if server is not None:
            try:
                server.close()
            except OSError:
                pass
        thread = self._thread
        self._thread = None
        if thread is not None:
            thread.join(timeout=1.0)
        if os.name != "nt":
            try:
                if self.socket_path.exists():
                    self.socket_path.unlink()
            except OSError:
                pass
        if self._lock_handle is not None:
            try:
                import fcntl

                fcntl.flock(self._lock_handle.fileno(), fcntl.LOCK_UN)
            except (ImportError, OSError):
                pass
            try:
                self._lock_handle.close()
            except OSError:
                pass
            self._lock_handle = None


def runtime_paths() -> tuple[Path, Path]:
    """Expose the default paths so callers and tests use the same rules."""
    return instance_socket(), data_dir() / "instance.lock"


if os.name != "posix":  # pragma: no cover - Ubuntu/macOS use the POSIX path
    logger.debug("SingleInstance uses a localhost TCP port on this platform")
