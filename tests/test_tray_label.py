from nm_shell.player import PlayerState
from nm_shell.tray import short_title


def test_short_title_has_no_prefix_or_artist() -> None:
    state = PlayerState.from_payload(
        {"title": "江流", "artists": ["重阀"], "song_id": 1, "duration": 220}
    )
    assert short_title(state) == "江流"


def test_short_title_truncates_to_eight_visible_characters() -> None:
    state = PlayerState.from_payload({"title": "我的家在东北2024", "song_id": 1})
    assert short_title(state) == "我的家在东北2…"
    assert len(short_title(state)) == 8


def test_short_title_keeps_exactly_eight_characters() -> None:
    state = PlayerState.from_payload({"title": "一二三四五六七八", "song_id": 1})
    assert short_title(state) == "一二三四五六七八"


def test_short_title_empty_state() -> None:
    assert short_title(PlayerState()) == "未在播放"
    assert short_title(PlayerState.from_payload({"title": "   ", "song_id": 1})) == "未在播放"
