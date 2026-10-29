"""
Split a runbook into chunks for retrieval.

The split follows the headings, so a chunk is one section (or one part of a long section) and carries its heading path,
for example "Database Connectivity > Diagnostic steps (read-only)". Long sections are cut at paragraph or line breaks
with a small overlap, so a sentence that sits on a boundary appears in both neighbours.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

_HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
_FENCE = re.compile(r"^\s*(```|~~~)")


@dataclass
class Chunk:
    ordinal: int
    heading: str
    text: str
    char_start: int
    char_end: int


def chunk_text(text: str, *, size: int = 900, overlap: int = 120) -> list[Chunk]:
    """Return chunks in document order. `size` is the target maximum length in characters."""
    overlap = min(overlap, size // 2)  # an overlap larger than half a chunk would make progress very slow
    sections = _sections(text)
    chunks: list[Chunk] = []
    for heading, body, start in sections:
        body_stripped = body.strip()
        if not body_stripped:
            continue
        for piece, offset in _split(body, size, overlap):
            piece_text = piece.strip()
            if not piece_text:
                continue
            begin = start + offset + (len(piece) - len(piece.lstrip()))
            chunks.append(Chunk(len(chunks), heading, piece_text, begin, begin + len(piece_text)))
    return chunks


def _sections(text: str) -> list[tuple[str, str, int]]:
    """List of (heading path, body text, start offset). Lines inside code fences are never treated as headings."""
    sections: list[tuple[str, str, int]] = []
    path: list[tuple[int, str]] = []
    current_start, current_lines, in_fence = 0, [], False
    position = 0

    def flush(end_heading: str) -> None:
        sections.append((end_heading, "".join(current_lines), current_start))

    heading_text = ""
    for line in text.splitlines(keepends=True):
        stripped = line.rstrip("\n")
        if _FENCE.match(stripped):
            in_fence = not in_fence
        match = None if in_fence else _HEADING.match(stripped)
        if match:
            flush(heading_text)
            level, title = len(match.group(1)), match.group(2)
            while path and path[-1][0] >= level:
                path.pop()
            path.append((level, title))
            heading_text = " > ".join(t for _, t in path)
            current_lines, current_start = [], position + len(line)
        else:
            current_lines.append(line)
        position += len(line)
    flush(heading_text)
    return sections


def _split(body: str, size: int, overlap: int) -> list[tuple[str, int]]:
    """Cut one section into pieces of at most `size` characters, preferring blank lines, then line ends."""
    if len(body) <= size:
        return [(body, 0)]
    pieces: list[tuple[str, int]] = []
    start = 0
    while start < len(body):
        end = min(start + size, len(body))
        if end < len(body):
            window = body[start:end]
            cut = max(window.rfind("\n\n"), window.rfind("\n"), window.rfind(". "))
            if cut > size // 2:  # only cut at a break that keeps the piece reasonably large
                end = start + cut + 1
        pieces.append((body[start:end], start))
        if end >= len(body):
            break
        start = max(end - overlap, start + 1)
    return pieces
