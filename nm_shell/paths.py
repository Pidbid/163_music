"""Filesystem locations used by the shell."""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "163-music"
APP_DISPLAY_NAME = "网易云音乐"
APP_VENDOR = "Pidbid"
APP_URL = "https://music.163.com/st/webplayer"

# Repository root in development; extraction root in a Nuitka onefile build.
_ROOT = Path(__file__).resolve().parent.parent

ICON_NAMES = ("icon.png", "icon.ico")


def resource_path(*parts: str) -> Path:
    """Return a bundled resource (ui/, assets/) in dev and frozen builds."""
    return _ROOT.joinpath(*parts)


def _xdg_dir(env_name: str, fallback: Path) -> Path:
    value = os.environ.get(env_name)
    return Path(value).expanduser() if value else fallback


def data_dir() -> Path:
    """Per-user writable state (logs, web engine profile, instance socket)."""
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        base = _xdg_dir("XDG_DATA_HOME", Path.home() / ".local" / "share")
    return base / APP_NAME


def cache_dir() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        base = _xdg_dir("XDG_CACHE_HOME", Path.home() / ".cache")
    return base / APP_NAME


def config_dir() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        base = _xdg_dir("XDG_CONFIG_HOME", Path.home() / ".config")
    return base / APP_NAME


def logs_dir() -> Path:
    return data_dir() / "logs"


def webengine_dir() -> Path:
    return data_dir() / "webengine"


def instance_socket() -> Path:
    if sys.platform == "darwin":
        # Unix socket paths are limited to ~104 bytes; the Application Support
        # path is usually longer, so keep the macOS socket under /tmp.
        return Path("/tmp") / f"{APP_NAME}-{os.getuid()}.sock"
    runtime = os.environ.get("XDG_RUNTIME_DIR")
    if runtime:
        return Path(runtime) / f"{APP_NAME}.sock"
    return data_dir() / "instance.sock"


def ensure_data_dirs() -> None:
    for path in (data_dir(), logs_dir(), config_dir(), webengine_dir()):
        path.mkdir(parents=True, exist_ok=True)


def icon_path() -> Path:
    """Prefer the PNG on Linux/macOS and the multi-size ICO on Windows."""
    if sys.platform == "win32":
        ico = resource_path("assets", "icon.ico")
        if ico.is_file():
            return ico
    for name in ICON_NAMES:
        candidate = resource_path("assets", name)
        if candidate.is_file():
            return candidate
    return resource_path("assets", "icon.png")
