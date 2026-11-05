from nm_shell.lyrics import (
    LyricLine,
    active_index,
    active_line,
    display_pair,
    parse_lrc,
    parse_lyrics_payload,
)


def test_parse_lrc_expands_multiple_timestamps_and_sorts() -> None:
    text = "[00:10.00][00:20.50]副歌\n[00:05.25]第一句\n[00:10.00]重复\n"
    assert parse_lrc(text) == [
        LyricLine(5.25, "第一句"),
        LyricLine(10.0, "副歌"),
        LyricLine(10.0, "重复"),
        LyricLine(20.5, "副歌"),
    ]


def test_parse_lrc_handles_offsets_metadata_and_junk() -> None:
    text = (
        "[offset:500]\n"
        "[ti:测试]\n"
        "[00:01.2]甲\n"
        "[00:02.345][00:03.0]乙\n"
        "没有时间戳的行\n"
        "[00:xx]坏行\n"
    )
    assert parse_lrc(text) == [
        LyricLine(1.7, "甲"),
        LyricLine(2.845, "乙"),
        LyricLine(3.5, "乙"),
    ]


def test_parse_lrc_decodes_entities_and_rejects_empty_text() -> None:
    assert parse_lrc("[00:01.00]Tom &amp; Jerry\n[00:02.00]   \n") == [
        LyricLine(1.0, "Tom & Jerry")
    ]


def test_active_index_boundaries() -> None:
    lines = [LyricLine(1.0, "a"), LyricLine(3.0, "b")]
    assert active_index(lines, 0.99) == -1
    assert active_index(lines, 1.0) == 0
    assert active_index(lines, 2.99) == 0
    assert active_index(lines, 3.0) == 1
    assert active_index(lines, 99.0) == 1
    assert active_index([], 1.0) == -1


def test_active_line_and_display_pair() -> None:
    lines = [LyricLine(1.0, "a"), LyricLine(3.0, "b")]
    assert active_line(lines, 2.0) == LyricLine(1.0, "a")
    assert active_line(lines, 0.5) is None
    assert display_pair(lines, 0.5) == ("", "a")
    assert display_pair(lines, 2.0) == ("a", "b")
    assert display_pair(lines, 4.0) == ("b", "")


def test_parse_lyrics_payload_tolerates_missing_shapes() -> None:
    assert parse_lyrics_payload({}) == []
    assert parse_lyrics_payload({"lrc": None}) == []
    assert parse_lyrics_payload({"lrc": {"lyric": None}}) == []
    assert parse_lyrics_payload({"lrc": {"lyric": "[00:01.00]hi"}}) == [LyricLine(1.0, "hi")]
