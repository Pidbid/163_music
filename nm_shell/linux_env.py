"""Linux environment knobs that must be in place before Qt loads.

QtWebEngine draws hover tooltips (and every other page popup) as their own
compositor surfaces. On this class of machine -- ARM64 with a mainline
``msm``/freedreno GPU, or any driver whose offscreen surfaces fail -- those
surfaces come out as opaque black boxes: the tooltip rectangle paints, the
text never does. On Wayland the same popups are additionally positioned by the
compositor instead of the app, which our frameless window cannot compensate.

Both are avoided the same way the author's ``dsh-shell`` does it:

* software rasterisation (``--disable-gpu``) so popups are painted by the
  software compositor instead of the GPU,
* the X11 platform (XWayland) when the session offers it, so popups are
  ordinary X windows.

This module only mutates ``os.environ``; it must be imported from
``nm_shell/__init__.py`` so it runs before PySide6/QtWebEngine is imported.

Overrides (both read at import time):

===========================  =====================================================
``NM_WEBENGINE_GPU=1``       keep Chromium's GPU compositor (tooltips may break)
``NM_WEBENGINE_PLATFORM=xcb``  force the X11 platform even without Wayland
``NM_WEBENGINE_PLATFORM=wayland``  keep native Wayland (popups compositor-placed)
===========================  =====================================================
"""

from __future__ import annotations

import ctypes.util
import os
import sys
from collections.abc import Mapping, MutableMapping

SOFTWARE_FLAG = "--disable-gpu"
GPU_ENV = "NM_WEBENGINE_GPU"
PLATFORM_ENV = "NM_WEBENGINE_PLATFORM"

_TRUTHY = {"1", "on", "true", "yes", "enable", "enabled"}
_FALSY = {"0", "off", "false", "no", "disable", "disabled"}


def _add_flag(value: str, flag: str) -> str:
    """Append ``flag`` to a space separated Chromium flag string, once."""
    tokens = value.split()
    if flag not in tokens:
        tokens.append(flag)
    return " ".join(tokens)


def wants_software_rendering(environ: Mapping[str, str]) -> bool:
    """Software rasterisation whenever the GPU compositor cannot be trusted."""
    requested = (environ.get(GPU_ENV) or "").strip().lower()
    if requested in _TRUTHY:
        return False
    if requested in _FALSY:
        return True
    return True  # Linux default: popups must paint even on broken GPU stacks


def xcb_platform_available() -> bool:
    """Qt's xcb plugin refuses to load without libxcb-cursor at runtime."""
    try:
        return bool(ctypes.util.find_library("xcb-cursor"))
    except (OSError, AttributeError):
        return False


def platform_choice(environ: Mapping[str, str]) -> str | None:
    """Return ``"xcb"`` when the app should run on X11, else ``None``."""
    requested = (environ.get(PLATFORM_ENV) or "").strip().lower()
    if requested in {"xcb", "x11"}:
        return "xcb"  # explicit request: trust it
    if requested in {"wayland", "native"}:
        return None
    if (environ.get("QT_QPA_PLATFORM") or "").strip():
        return None  # the desktop or the user already picked a platform
    if not (environ.get("WAYLAND_DISPLAY") and environ.get("DISPLAY")):
        return None
    return "xcb" if xcb_platform_available() else None


def linux_bootstrap(
    environ: MutableMapping[str, str] | None = None,
    platform: str | None = None,
) -> dict[str, str]:
    """Apply the Linux QtWebEngine settings; returns what was changed."""
    env = os.environ if environ is None else environ
    current_platform = sys.platform if platform is None else platform
    if not current_platform.startswith("linux"):
        return {}

    applied: dict[str, str] = {}

    if wants_software_rendering(env):
        merged = _add_flag(env.get("QTWEBENGINE_CHROMIUM_FLAGS", ""), SOFTWARE_FLAG)
        if merged != env.get("QTWEBENGINE_CHROMIUM_FLAGS"):
            env["QTWEBENGINE_CHROMIUM_FLAGS"] = merged
            applied["QTWEBENGINE_CHROMIUM_FLAGS"] = merged

    if platform_choice(env) == "xcb":
        env["QT_QPA_PLATFORM"] = "xcb"
        applied["QT_QPA_PLATFORM"] = "xcb"

    return applied
