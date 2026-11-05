import shutil
import sys
import tempfile
import threading
import time
from pathlib import Path

import pytest

from nm_shell.single_instance import SingleInstance

pytestmark = pytest.mark.skipif(
    sys.platform == "win32",
    reason="the Windows backend uses a localhost TCP lock instead of Unix sockets",
)


@pytest.fixture
def short_paths():
    root = Path(tempfile.mkdtemp(prefix="nm-", dir="/tmp"))
    try:
        yield root / "shell.sock", root / "shell.lock"
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_second_instance_notifies_primary(short_paths) -> None:
    socket_path, lock_path = short_paths
    received: list[str] = []
    delivered = threading.Event()

    primary = SingleInstance(socket_path=socket_path, lock_path=lock_path)
    assert primary.acquire() is True
    assert primary.start_server(lambda command: (received.append(command), delivered.set())) is True

    secondary = SingleInstance(socket_path=socket_path, lock_path=lock_path)
    assert secondary.acquire() is False
    assert secondary.notify_primary("show") is True
    assert delivered.wait(timeout=2.0)
    assert received == ["show"]

    secondary.close()
    primary.close()
    assert not socket_path.exists()


def test_acquire_is_exclusive_when_primary_closes(short_paths) -> None:
    socket_path, lock_path = short_paths

    first = SingleInstance(socket_path=socket_path, lock_path=lock_path)
    assert first.acquire() is True
    second = SingleInstance(socket_path=socket_path, lock_path=lock_path)
    assert second.acquire() is False
    first.close()
    time.sleep(0.05)
    assert second.acquire() is True
    second.close()
