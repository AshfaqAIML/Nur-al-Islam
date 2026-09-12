"""Structure-aware chunking — chapters/sections/paragraphs/quotations first.

Default unit is the PAGE (one SearchDocument per processed page): a physical,
provenance-exact unit that never splits unrelated text. split_paragraphs()
offers finer structural chunks for long pages — each chunk inherits the full
page provenance plus paragraph offsets. Quotation spans (Arabic quote marks
“…” / «…» / "..." and Quranic ۝ markers) are detected so indexers can keep
quotations intact; nothing is ever reordered or merged across pages.
"""
from __future__ import annotations

import re

QUOTE_RES = [
    re.compile(r"\"([^\"]{10,2000})\""),
    re.compile(r"“([^”]{10,2000})”"),
    re.compile(r"«([^»]{10,2000})»"),
    re.compile(r"﴿([^﴾]{10,2000})﴾"),
]


def split_paragraphs(text: str) -> list[dict]:
    """Split on blank lines; record char offsets. Drops empties."""
    chunks: list[dict] = []
    cursor = 0
    for para in re.split(r"\n\s*\n", text):
        start = text.find(para, cursor)
        stripped = para.strip()
        if stripped:
            chunks.append({"text": stripped, "start": start, "end": start + len(para)})
        cursor = start + len(para)
    return chunks


def find_quotations(text: str) -> list[dict]:
    """Quotation spans with offsets — kept intact by chunkers downstream."""
    out: list[dict] = []
    for rx in QUOTE_RES:
        for m in rx.finditer(text):
            out.append({"text": m.group(1), "start": m.start(), "end": m.end()})
    # Quranic end-of-ayah marker ۝ (U+06DD) — verse span = line containing it
    for m in re.finditer(r"[^\n]*\u06DD[^\n]*", text):
        out.append({"text": m.group(0).strip(), "start": m.start(), "end": m.end(), "quranic": True})
    return out


def build_chunk(
    text: str,
    provenance: dict,
    kind: str = "page",
    start: int | None = None,
    end: int | None = None,
) -> dict:
    """One indexable chunk: display text + full provenance. No text is altered."""
    return {
        "kind": kind,  # page | paragraph
        "text": text,
        "start": start,
        "end": end,
        # provenance — every key traceable, unknown stays None
        "bookId": provenance.get("bookId"),
        "volume": provenance.get("volume"),
        "chapter": provenance.get("chapter"),
        "section": provenance.get("section"),
        "pageNumber": provenance.get("pageNumber"),
        "pdfPage": provenance.get("pdfPage"),
        "pageId": provenance.get("pageId"),
        "jobId": provenance.get("jobId"),
        "engine": provenance.get("engine"),
        "model": provenance.get("model"),
        "surah": provenance.get("surah"),
        "ayahStart": provenance.get("ayahStart"),
        "ayahEnd": provenance.get("ayahEnd"),
        "juz": provenance.get("juz"),
        "ruku": provenance.get("ruku"),
        "masala": provenance.get("masala"),
    }


def chunk_page(text: str, provenance: dict, min_paragraph_chars: int = 0) -> list[dict]:
    """Page-level chunk + optional paragraph children.

    Always emits exactly one `page` chunk (the indexed unit). Paragraph
    chunks are emitted only for paragraphs ≥ min_paragraph_chars (0 = off),
    each inheriting full provenance — used for preview/long-page handling,
    never as a substitute for the page chunk.
    """
    chunks = [build_chunk(text, provenance, kind="page", start=0, end=len(text))]
    if min_paragraph_chars > 0:
        for p in split_paragraphs(text):
            if len(p["text"]) >= min_paragraph_chars:
                chunks.append(build_chunk(p["text"], provenance, kind="paragraph", start=p["start"], end=p["end"]))
    return chunks
