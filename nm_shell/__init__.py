"""Unofficial NetEase Cloud Music web player shell."""

from __future__ import annotations

from .linux_env import linux_bootstrap

# Qt/QtWebEngine read these once, at import time, so this has to happen before
# anything pulls PySide6 in. See nm_shell/linux_env.py for the why.
BOOTSTRAP = linux_bootstrap()
