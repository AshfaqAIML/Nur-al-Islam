"""Index-time text + chunk builders for the reindex path.

Display text stays verbatim (server stores it in SearchDocument.body);
search_text() feeds bodySearch. build_doc() mirrors the server reindex
shape (entityType BOOK_PAGE) so tests assert the exact contract.
"""
from __future__ import annotations

from normalize import normalize_text
from structure import build_chunk


def search_text(raw: str) -> str:
    return normalize_text(raw, strip_tashkeel=True)


def build_doc(
    page_id: str,
    display: str,
    title: str,
    route: str,
    language: str,
    book_id: str,
    provenance: dict,
) -> dict:
    """Mirror of POST /api/admin/reindex document shape (contract test target)."""
    meta = {
        "volume": provenance.get("volume"),
        "pageNumber": provenance.get("pageNumber"),
        "chapter": provenance.get("chapter"),
        "section": provenance.get("section"),
        "jild": provenance.get("jild"),
        "surah": provenance.get("surah"),
        "ayahStart": provenance.get("ayahStart"),
        "ayahEnd": provenance.get("ayahEnd"),
        "juz": provenance.get("juz"),
        "ruku": provenance.get("ruku"),
        "masala": provenance.get("masala"),
        "jobId": provenance.get("jobId"),
        "engine": provenance.get("engine"),
        "model": provenance.get("model"),
        "checksum": provenance.get("checksum"),
        "language": provenance.get("language"),
        "textState": provenance.get("textState", "raw"),
        "verified": provenance.get("verified", False),
        "ocrConfidence": provenance.get("ocrConfidence"),
        "signals": provenance.get("signals"),
    }
    chunk = build_chunk(display, {**provenance, "pageId": page_id})
    return {
        "entityType": "BOOK_PAGE",
        "entityId": page_id,
        "title": title,
        "body": display,
        "bodySearch": search_text(display),
        "language": language,
        "route": route,
        "weight": 1,
        "bookId": book_id,
        "meta": meta,
        "chunkKind": chunk["kind"],
    }
