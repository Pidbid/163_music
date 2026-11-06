import sys

from nm_shell.webview_app import build_chrome_script


def test_chrome_script_replaces_platform_placeholders() -> None:
    script = build_chrome_script()

    assert "__NM_ICON_DATA_URI__" not in script
    assert "__NM_ROUNDED_WINDOW__" not in script
    assert "data:image/png;base64," in script
    assert "nm-shell-bar" in script

    expected = "true" if sys.platform.startswith("linux") else "false"
    assert f'var ROUNDED_WINDOW = "{expected}" === "true";' in script
