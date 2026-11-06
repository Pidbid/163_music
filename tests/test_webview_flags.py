import os

from nm_shell import webview_app

MEDIA_KEY_FLAG = "--disable-features=HardwareMediaKeyHandling"


def _flags(monkeypatch, platform: str, current: str | None = None) -> list[str]:
    monkeypatch.setattr(webview_app.sys, "platform", platform)
    if current is None:
        monkeypatch.delenv("QTWEBENGINE_CHROMIUM_FLAGS", raising=False)
    else:
        monkeypatch.setenv("QTWEBENGINE_CHROMIUM_FLAGS", current)
    webview_app._set_chromium_flags()
    return os.environ["QTWEBENGINE_CHROMIUM_FLAGS"].split()


def test_linux_disables_chromium_media_key_mpris(monkeypatch) -> None:
    flags = _flags(monkeypatch, "linux")
    assert MEDIA_KEY_FLAG in flags


def test_existing_disable_features_are_merged(monkeypatch) -> None:
    flags = _flags(
        monkeypatch,
        "linux",
        "--disable-features=SomeFeature,OtherFeature --enable-logging",
    )
    disable = [f for f in flags if f.startswith("--disable-features=")]
    assert len(disable) == 1
    assert set(disable[0].split("=", 1)[1].split(",")) == {
        "SomeFeature",
        "OtherFeature",
        "HardwareMediaKeyHandling",
    }
    assert "--enable-logging" in flags


def test_flags_are_idempotent(monkeypatch) -> None:
    _flags(monkeypatch, "linux")
    webview_app._set_chromium_flags()
    assert os.environ["QTWEBENGINE_CHROMIUM_FLAGS"].split().count(MEDIA_KEY_FLAG) == 1


def test_non_linux_keeps_chromium_media_keys(monkeypatch) -> None:
    flags = _flags(monkeypatch, "win32")
    assert not any("HardwareMediaKeyHandling" in flag for flag in flags)
