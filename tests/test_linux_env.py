import os

import pytest

from nm_shell import linux_env


def _env(**overrides: str) -> dict[str, str]:
    base = {"DISPLAY": ":0"}
    base.update(overrides)
    return base


def test_linux_defaults_to_software_rendering() -> None:
    environ = _env()
    applied = linux_env.linux_bootstrap(environ, "linux")
    flags = environ["QTWEBENGINE_CHROMIUM_FLAGS"].split()
    assert "--disable-gpu" in flags
    assert applied["QTWEBENGINE_CHROMIUM_FLAGS"] == "--disable-gpu"


def test_existing_flags_are_kept_and_software_flag_added_once() -> None:
    environ = _env(QTWEBENGINE_CHROMIUM_FLAGS="--enable-logging --disable-gpu")
    linux_env.linux_bootstrap(environ, "linux")
    flags = environ["QTWEBENGINE_CHROMIUM_FLAGS"].split()
    assert flags.count("--disable-gpu") == 1
    assert "--enable-logging" in flags
    assert flags[0] == "--enable-logging"


def test_gpu_override_keeps_the_compositor(monkeypatch: pytest.MonkeyPatch) -> None:
    environ = _env(**{linux_env.GPU_ENV: "1"})
    applied = linux_env.linux_bootstrap(environ, "linux")
    assert "QTWEBENGINE_CHROMIUM_FLAGS" not in applied
    assert "QTWEBENGINE_CHROMIUM_FLAGS" not in environ


def test_explicit_software_override_on_a_gpu_capable_platform() -> None:
    environ = _env(**{linux_env.GPU_ENV: "off"})
    linux_env.linux_bootstrap(environ, "linux")
    assert "--disable-gpu" in environ["QTWEBENGINE_CHROMIUM_FLAGS"].split()


def test_wayland_session_with_xwayland_gets_the_x11_platform(monkeypatch) -> None:
    monkeypatch.setattr(linux_env, "xcb_platform_available", lambda: True)
    environ = _env(WAYLAND_DISPLAY="wayland-0")
    applied = linux_env.linux_bootstrap(environ, "linux")
    assert environ["QT_QPA_PLATFORM"] == "xcb"
    assert applied["QT_QPA_PLATFORM"] == "xcb"


def test_missing_xcb_cursor_library_keeps_the_desktop_platform(monkeypatch) -> None:
    """A missing libxcb-cursor makes Qt abort on start, so do not switch."""
    monkeypatch.setattr(linux_env, "xcb_platform_available", lambda: False)
    environ = _env(WAYLAND_DISPLAY="wayland-0")
    linux_env.linux_bootstrap(environ, "linux")
    assert "QT_QPA_PLATFORM" not in environ


def test_explicit_xcb_request_does_not_need_the_library_probe(monkeypatch) -> None:
    monkeypatch.setattr(linux_env, "xcb_platform_available", lambda: False)
    environ = _env(**{linux_env.PLATFORM_ENV: "xcb"})
    linux_env.linux_bootstrap(environ, "linux")
    assert environ["QT_QPA_PLATFORM"] == "xcb"


def test_pure_wayland_session_is_left_alone() -> None:
    environ = {"WAYLAND_DISPLAY": "wayland-0"}
    linux_env.linux_bootstrap(environ, "linux")
    assert "QT_QPA_PLATFORM" not in environ


def test_pure_x11_session_is_left_alone() -> None:
    environ = _env()
    linux_env.linux_bootstrap(environ, "linux")
    assert "QT_QPA_PLATFORM" not in environ


def test_explicit_platform_from_the_environment_wins() -> None:
    environ = _env(WAYLAND_DISPLAY="wayland-0", QT_QPA_PLATFORM="wayland")
    linux_env.linux_bootstrap(environ, "linux")
    assert environ["QT_QPA_PLATFORM"] == "wayland"


def test_platform_override_can_keep_native_wayland() -> None:
    environ = _env(WAYLAND_DISPLAY="wayland-0", **{linux_env.PLATFORM_ENV: "wayland"})
    linux_env.linux_bootstrap(environ, "linux")
    assert "QT_QPA_PLATFORM" not in environ


def test_non_linux_is_untouched() -> None:
    for platform in ("win32", "darwin"):
        environ = _env(WAYLAND_DISPLAY="wayland-0")
        assert linux_env.linux_bootstrap(environ, platform) == {}
        assert environ == _env(WAYLAND_DISPLAY="wayland-0")


@pytest.mark.skipif(not os.sys.platform.startswith("linux"), reason="linux only")
def test_importing_the_package_configures_the_process() -> None:
    """The point of the module is that importing nm_shell is enough."""
    import nm_shell

    assert nm_shell.BOOTSTRAP, "bootstrap did not report any change"
    assert "--disable-gpu" in os.environ["QTWEBENGINE_CHROMIUM_FLAGS"].split()
