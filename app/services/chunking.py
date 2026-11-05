"""版本化的确定性原文切片；坐标始终使用 Unicode 码点。"""

import json
import re
from dataclasses import dataclass
from hashlib import sha256
from uuid import UUID, uuid5

from app.services.access import AccessDenied

SOURCE_LIMIT = 32_000
CHUNK_LIMIT = 64
CHUNK_NAMESPACE = UUID("f2a886c9-bc0b-52d3-8f02-4687baf69642")


def invalid(message):
    return AccessDenied(400, 1000, message)


@dataclass(frozen=True)
class ChunkConfig:
    mode: str = "auto"
    window: int = 600
    overlap: int = 80

    def __post_init__(self):
        if self.mode not in ("auto", "custom", "title"):
            raise invalid("切片方式无效")
        if self.mode != "custom" and (self.window, self.overlap) != (600, 80):
            raise invalid("自动和标题切片使用固定窗口 600、重叠 80")
        if (
            type(self.window) is not int
            or not 100 <= self.window <= 1200
            or type(self.overlap) is not int
            or not 0 <= self.overlap <= min(200, self.window - 1)
        ):
            raise invalid("窗口须为 100 至 1200，重叠须在允许范围内")

    @property
    def version(self):
        value = {
            "algorithm": "slice-v1",
            "headings": "headings-v1",
            "mode": self.mode,
            "window": self.window,
            "overlap": self.overlap,
            "source_limit": SOURCE_LIMIT,
            "chunk_limit": CHUNK_LIMIT,
        }
        return sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


@dataclass(frozen=True)
class Chunk:
    id: str
    ordinal: int
    start: int
    end: int
    text: str


def _windows(text, start, end, config, *, prefer_lines):
    while start < end:
        stop = min(start + config.window, end)
        if prefer_lines and stop < end:
            # 保证重叠后仍前进；优先段落，再选行末。
            minimum = start + max(config.overlap + 1, config.window // 2)
            boundaries = [
                match.end() + start
                for match in re.finditer(r"\r?\n[ \t]*\r?\n", text[start:stop])
                if match.end() + start >= minimum
            ]
            if boundaries:
                stop = boundaries[-1]
            else:
                newline = text.rfind("\n", minimum, stop)
                if newline >= minimum:
                    stop = newline + 1
        if text[start:stop].strip():
            yield start, stop
        if stop == end:
            break
        start = stop - config.overlap


def _headings(text):
    """headings-v1：ATX/Setext 标题，忽略围栏代码和四空格缩进。"""
    offsets = []
    position = 0
    fence = None
    paragraph = None
    for line in text.splitlines(keepends=True):
        value = line.rstrip("\r\n")
        marker = re.match(r"^ {0,3}(`{3,}|~{3,})(.*)$", value)
        if fence:
            if (
                marker
                and marker[1][0] == fence[0]
                and len(marker[1]) >= fence[1]
                and not marker[2].strip()
            ):
                fence = None
            paragraph = None
        elif marker and (marker[1][0] != "`" or "`" not in marker[2]):
            fence = marker[1][0], len(marker[1])
            paragraph = None
        elif re.match(r"^ {0,3}#{1,6}(?:[ \t]|$)", value):
            offsets.append(position)
            paragraph = None
        elif paragraph is not None and re.fullmatch(r" {0,3}(?:=+|-+)[ \t]*", value):
            offsets.append(paragraph)
            paragraph = None
        elif not value.strip() or value.startswith(("    ", "\t")):
            paragraph = None
        elif paragraph is None:
            paragraph = position
        position += len(line)
    return sorted({0, *offsets, len(text)})


def split_source(raw, source_format, material_id, index_version, config=None):
    config = config or ChunkConfig()
    if source_format not in ("text", "txt", "md"):
        raise invalid("原文格式不支持切片")
    if config.mode == "title" and source_format != "md":
        raise invalid("标题切片仅支持 Markdown")
    try:
        text = raw.decode("utf-8-sig")
        material_id = str(UUID(material_id))
    except (UnicodeError, ValueError):
        raise invalid("原文须为 UTF-8，资料标识须有效") from None
    if not text.strip() or "\0" in text:
        raise invalid("原文不能为空白或包含空字符")
    if len(text) > SOURCE_LIMIT:
        raise invalid("原文超过 32,000 码点，请按章节拆成多份资料")
    if type(index_version) is not int or index_version < 1:
        raise invalid("索引版本须为正整数")
    boundaries = _headings(text) if config.mode == "title" else [0, len(text)]
    intervals = [
        interval
        for start, end in zip(boundaries, boundaries[1:], strict=False)
        for interval in _windows(
            text, start, end, config, prefer_lines=config.mode != "custom"
        )
    ]
    if len(intervals) > CHUNK_LIMIT and config.mode == "auto":
        intervals = list(_windows(text, 0, len(text), config, prefer_lines=False))
    if len(intervals) > CHUNK_LIMIT:
        raise invalid("切片超过 64 片，请改用自动模式")
    return [
        Chunk(
            str(uuid5(CHUNK_NAMESPACE, f"{material_id}:{index_version}:{ordinal}")),
            ordinal,
            start,
            end,
            text[start:end],
        )
        for ordinal, (start, end) in enumerate(intervals)
    ]
