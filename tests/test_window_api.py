from nm_shell.window_api import ShellApi


class FakeWindow:
    def __init__(self, answer: bool) -> None:
        self.answer = answer
        self.scripts: list[str] = []

    def evaluate_js(self, script: str) -> bool:
        self.scripts.append(script)
        return self.answer


def test_player_action_returns_the_page_answer() -> None:
    api = ShellApi()
    api.bind(FakeWindow(True))
    assert api.player_action("next") is True


def test_player_action_reports_a_missing_button() -> None:
    # The page restores its player after a restart; until its footer exists the
    # injected action returns false and the shell retries.
    api = ShellApi()
    api.bind(FakeWindow(False))
    assert api.player_action("toggle") is False
