from nm_shell.player import PlayerState, parse_clock, parse_percent


def test_parse_clock_supports_minutes_and_hours() -> None:
    assert parse_clock("03:40") == 220.0
    assert parse_clock("00:07") == 7.0
    assert parse_clock("1:02:03") == 3723.0
    assert parse_clock("  02:42 ") == 162.0
    assert parse_clock("") is None
    assert parse_clock("03:xx") is None
    assert parse_clock("03:60") is None
    assert parse_clock("-1:00") is None


def test_parse_percent_only_accepts_visible_range() -> None:
    assert parse_percent("74.50%") == 74.5
    assert parse_percent("0%") == 0.0
    assert parse_percent("100%") == 100.0
    assert parse_percent("101%") is None
    assert parse_percent("-1%") is None
    assert parse_percent("abc") is None
    assert parse_percent(None) is None


def test_state_normalizes_payload_and_clamps_position() -> None:
    state = PlayerState.from_payload(
        {
            "title": "  江流  ",
            "artists": ["重阀", "", 3],
            "album": "长嘉十卷",
            "song_id": "3424705683",
            "duration": "220",
            "position": 999,
            "playing": 1,
            "cover": "https://p2.music.126.net/cover.jpg",
        }
    )
    assert state.title == "江流"
    assert state.artists == ("重阀", "3")
    assert state.album == "长嘉十卷"
    assert state.song_id == 3424705683
    assert state.duration == 220.0
    assert state.position == 220.0
    assert state.playing is True
    assert state.cover == "https://p2.music.126.net/cover.jpg"
    assert state.display_label == "江流 - 重阀 / 3"


def test_state_rejects_invalid_ids_and_covers() -> None:
    state = PlayerState.from_payload(
        {
            "title": "x" * 400,
            "artists": "not-a-list",
            "song_id": "abc",
            "duration": -5,
            "position": -1,
            "cover": "javascript:alert(1)",
        }
    )
    assert len(state.title) == 300
    assert state.artists == ()
    assert state.song_id is None
    assert state.duration == 0.0
    assert state.position == 0.0
    assert state.cover == ""


def test_state_roundtrip_and_empty_label() -> None:
    state = PlayerState.from_payload(
        {
            "title": "江流",
            "artists": ["重阀"],
            "song_id": 3424705683,
            "duration": 220,
            "position": 42.5,
            "playing": True,
            "cover": "https://p2.music.126.net/cover.jpg",
        }
    )
    restored = PlayerState.from_payload(state.to_payload())
    assert restored.title == state.title
    assert restored.artists == state.artists
    assert restored.song_id == state.song_id
    assert restored.duration == state.duration
    assert restored.position == state.position
    assert restored.playing is True
    assert PlayerState().display_label == "未在播放"
    assert PlayerState().is_empty is True
