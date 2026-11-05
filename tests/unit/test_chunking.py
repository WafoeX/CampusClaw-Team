from dataclasses import replace
from uuid import UUID

import pytest

from app.services.access import AccessDenied
from app.services.chunking import ChunkConfig, split_source
from app.services.index_scope import IndexScope

MATERIAL = "00000000-0000-0000-0000-000000000001"


def split(text, mode="auto", **parameters):
    return split_source(
        text.encode("utf-8"), "md", MATERIAL, 1, ChunkConfig(mode, **parameters)
    )


def test_IX_N01_source_coordinates_preserve_bom_crlf_emoji_and_combining_marks():
    source = "前言😀e\u0301\r\n" * 120
    raw = b"\xef\xbb\xbf" + source.encode()
    chunks = split_source(raw, "txt", MATERIAL, 1)
    covered = set()
    for ordinal, chunk in enumerate(chunks):
        assert chunk.text == source[chunk.start : chunk.end]
        assert chunk.ordinal == ordinal and str(UUID(chunk.id)) == chunk.id
        assert chunk.end - chunk.start == len(chunk.text) <= 600
        covered.update(range(chunk.start, chunk.end))
    assert covered == set(range(len(source)))
    assert raw == b"\xef\xbb\xbf" + source.encode()
    assert "\r\n" in chunks[0].text and "e\u0301" in chunks[0].text


def test_IX_N01_custom_windows_overlap_and_end_exactly_once():
    chunks = split("甲" * 250, "custom", window=100, overlap=20)
    assert [(chunk.start, chunk.end) for chunk in chunks] == [
        (0, 100),
        (80, 180),
        (160, 250),
    ]


def test_IX_N01_auto_prefers_paragraph_then_line_boundaries():
    text = "甲" * 350 + "\r\n\r\n" + "乙" * 350 + "\n" + "丙" * 350
    chunks = split(text)
    assert chunks[0].end == 354 and chunks[1].start == 274
    assert chunks[1].end == 705
    assert all(chunk.text == text[chunk.start : chunk.end] for chunk in chunks)


def test_IX_N01_title_preserves_preamble_and_ignores_fenced_fake_headings():
    sections = [
        "前言😀\r\n\r\n",
        "# 第一章\r\n正文\r\n```md\r\n# 假标题\r\n```\r\n",
        "第二章\r\n===\r\n结尾\r\n~~~\r\n伪标题\r\n---\r\n~~~\r\n",
    ]
    chunks = split("".join(sections), "title")
    assert [chunk.text for chunk in chunks] == sections


def test_IX_N01_title_without_heading_uses_auto_and_long_section_is_bounded():
    text = "正文😀" * 500
    assert split(text, "title") == split(text)
    chunks = split("# 章节\n" + text, "title")
    assert chunks[0].text.startswith("# 章节\n")
    assert chunks[-1].end == len("# 章节\n" + text)
    assert max(len(chunk.text) for chunk in chunks) <= 600


def test_IX_N01_ids_replay_and_change_only_with_material_or_index_version():
    raw = "相同文本".encode()
    first = split_source(raw, "text", MATERIAL, 1)
    assert split_source(raw, "text", MATERIAL, 1) == first
    assert split_source(raw, "text", MATERIAL, 2)[0].id != first[0].id
    assert (
        split_source(raw, "text", "00000000-0000-0000-0000-000000000002", 1)[0].id
        != first[0].id
    )
    assert ChunkConfig().version == ChunkConfig().version
    assert ChunkConfig().version != ChunkConfig("custom").version


def test_IX_B01_exactly_64_chunks_and_maximum_custom_window():
    assert len(split("甲" * 6400, "custom", window=100, overlap=0)) == 64
    assert len(split("甲" * 1200, "custom", window=1200, overlap=200)) == 1


def test_IX_B02_32000_codepoints_falls_back_without_truncation():
    text = ("甲" * 300 + "\n\n") * 105
    text += "乙" * (32000 - len(text))
    chunks = split(text)
    assert len(chunks) == 62
    assert (chunks[0].start, chunks[0].end) == (0, 600)
    assert chunks[-1].end == 32000
    covered = {index for chunk in chunks for index in range(chunk.start, chunk.end)}
    assert covered == set(range(32000))
    assert all(chunk.text == text[chunk.start : chunk.end] for chunk in chunks)


def test_IX_B02_32001_rejected_before_constructing_any_chunk():
    with pytest.raises(AccessDenied, match="按章节拆") as caught:
        split("😀" * 32001)
    assert caught.value.status == 400 and caught.value.code == 1000


@pytest.mark.parametrize(
    "config",
    [
        {"mode": "invalid"},
        {"mode": "custom", "window": 99},
        {"mode": "custom", "window": 1201},
        {"mode": "custom", "overlap": 201},
        {"mode": "custom", "window": 100, "overlap": 100},
        {"mode": "custom", "window": True},
        {"mode": "custom", "overlap": False},
        {"mode": "auto", "window": 500},
    ],
)
def test_IX_F01_invalid_config_rejected(config):
    with pytest.raises(AccessDenied) as caught:
        ChunkConfig(**config)
    assert caught.value.code == 1000


@pytest.mark.parametrize(
    "source,mode", [("甲" * 6500, "custom"), ("# 章\n正文\n" * 65, "title")]
)
def test_IX_F01_65_chunks_rejected_with_auto_hint(source, mode):
    parameters = {"window": 100, "overlap": 0} if mode == "custom" else {}
    with pytest.raises(AccessDenied, match="自动模式"):
        split(source, mode, **parameters)


def test_IX_F01_title_on_txt_invalid_utf8_and_whitespace():
    for raw, source_format, config in [
        (b"text", "txt", ChunkConfig("title")),
        (b"\xff", "md", ChunkConfig()),
        (b" \r\n", "md", ChunkConfig()),
    ]:
        with pytest.raises(AccessDenied):
            split_source(raw, source_format, MATERIAL, 1, config)


def test_IX_N01_scope_payload_has_no_text_and_separates_all_versions():
    scope = IndexScope("class-a", MATERIAL, 1, 1, ChunkConfig().version)
    payload = scope.payload("chunk-id")
    assert payload == {**scope.fields, "scope_key": scope.key, "chunk_id": "chunk-id"}
    assert set(payload) == {
        "class_id",
        "material_id",
        "source_version",
        "index_version",
        "index_config_version",
        "scope_key",
        "chunk_id",
    }
    for changes in (
        {"class_id": "class-b"},
        {"source_version": 2},
        {"index_version": 2},
        {"index_config_version": "another"},
    ):
        assert replace(scope, **changes).key != scope.key
