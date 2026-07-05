"""
Layer 1 — Knowledge Ingestion: chunking.

Chunks documents by semantic section (background / methods / findings /
conclusion for PubMed abstracts; heading-based for guideline pages) rather
than a fixed character count. Fixed-size chunking regularly splits a finding
away from the qualifier that changes its meaning ("effective in patients
under 40" gets cut after "effective") — section-aware chunking keeps that
kind of claim intact.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass

# Common structured-abstract section headers in biomedical literature.
ABSTRACT_SECTION_HEADERS = [
    "BACKGROUND", "OBJECTIVE", "OBJECTIVES", "INTRODUCTION",
    "METHODS", "MATERIALS AND METHODS", "DESIGN",
    "RESULTS", "FINDINGS",
    "CONCLUSION", "CONCLUSIONS", "DISCUSSION",
]

_HEADER_PATTERN = re.compile(
    r"(?P<header>" + "|".join(ABSTRACT_SECTION_HEADERS) + r")\s*:\s*",
    flags=re.IGNORECASE,
)

# Guideline PDFs tend to use short Title Case or ALL CAPS lines as headings.
_GUIDELINE_HEADING_PATTERN = re.compile(r"^(?:[A-Z][A-Za-z0-9 /&\-]{2,60})$")

MAX_CHUNK_CHARS = 1200  # soft cap; only splits a section further if it's long


@dataclass
class Chunk:
    text: str
    section: str          # e.g. "background", "methods", "findings", "unlabeled"
    chunk_index: int
    metadata: dict

    def to_dict(self) -> dict:
        d = asdict(self)
        return d


def chunk_structured_abstract(abstract: str, metadata: dict) -> list[Chunk]:
    """Split a PubMed abstract on its own labeled sections, if present.
    Falls back to paragraph splitting if no section headers are found."""
    matches = list(_HEADER_PATTERN.finditer(abstract))

    if not matches:
        return chunk_by_paragraph(abstract, metadata)

    chunks: list[Chunk] = []
    for idx, m in enumerate(matches):
        section_name = m.group("header").lower()
        start = m.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(abstract)
        text = abstract[start:end].strip()
        if not text:
            continue
        for sub_idx, sub_text in enumerate(_split_if_too_long(text)):
            chunks.append(
                Chunk(
                    text=sub_text,
                    section=_normalize_section(section_name),
                    chunk_index=len(chunks),
                    metadata=metadata,
                )
            )
    return chunks


def chunk_by_paragraph(text: str, metadata: dict) -> list[Chunk]:
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    if len(paragraphs) <= 1:
        paragraphs = [text.strip()]

    chunks: list[Chunk] = []
    for para in paragraphs:
        for sub_text in _split_if_too_long(para):
            chunks.append(
                Chunk(text=sub_text, section="unlabeled", chunk_index=len(chunks), metadata=metadata)
            )
    return chunks


def chunk_guideline_page(page_text: str, metadata: dict) -> list[Chunk]:
    """Chunk a guideline PDF page on detected heading lines; falls back to
    paragraph splitting if no headings are detected on the page."""
    lines = page_text.split("\n")
    sections: list[tuple[str, list[str]]] = []
    current_heading = "unlabeled"
    current_lines: list[str] = []

    for line in lines:
        stripped = line.strip()
        if stripped and _GUIDELINE_HEADING_PATTERN.match(stripped) and len(stripped.split()) <= 8:
            if current_lines:
                sections.append((current_heading, current_lines))
            current_heading = stripped.lower()
            current_lines = []
        else:
            current_lines.append(line)
    if current_lines:
        sections.append((current_heading, current_lines))

    chunks: list[Chunk] = []
    for heading, body_lines in sections:
        body = "\n".join(body_lines).strip()
        if not body:
            continue
        for sub_text in _split_if_too_long(body):
            chunks.append(
                Chunk(text=sub_text, section=heading, chunk_index=len(chunks), metadata=metadata)
            )
    return chunks


def _normalize_section(raw: str) -> str:
    raw = raw.lower()
    if raw in ("objective", "objectives", "introduction"):
        return "background"
    if raw in ("materials and methods", "design"):
        return "methods"
    if raw == "findings":
        return "results"
    if raw == "discussion":
        return "conclusion"
    return raw


def _split_if_too_long(text: str) -> list[str]:
    if len(text) <= MAX_CHUNK_CHARS:
        return [text]
    sentences = re.split(r"(?<=[.!?])\s+", text)
    out: list[str] = []
    buf = ""
    for s in sentences:
        if len(buf) + len(s) + 1 > MAX_CHUNK_CHARS and buf:
            out.append(buf.strip())
            buf = s
        else:
            buf = f"{buf} {s}".strip()
    if buf:
        out.append(buf.strip())
    return out
