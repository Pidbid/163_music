from nm_shell.mpris import MprisRoot


def test_identity_uses_app_name() -> None:
    root = MprisRoot(lambda command: None, lambda: None)
    assert root.Identity == "163-music"


def test_desktop_entry_does_not_override_identity() -> None:
    root = MprisRoot(lambda command: None, lambda: None)
    assert root.DesktopEntry == ""
