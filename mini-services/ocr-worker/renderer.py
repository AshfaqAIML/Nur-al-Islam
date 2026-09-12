"""Incremental PDF access — never loads a whole book into RAM.

PyMuPDF opens documents lazily; each page is rendered on demand and the
pixmap is released by the caller. The runner processes pages strictly
one-at-a-time (see runner.py).
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

import fitz  # PyMuPDF
from PIL import Image


@contextmanager
def open_pdf(path: str) -> Iterator[fitz.Document]:
    doc = fitz.open(path)
    try:
        yield doc
    finally:
        doc.close()


def document_info(doc: fitz.Document) -> dict:
    meta = doc.metadata or {}
    return {
        "page_count": doc.page_count,
        "title": meta.get("title"),
        "author": meta.get("author"),
        "is_pdf": doc.is_pdf,
        "needs_pass": doc.needs_pass,
    }


def render_page(doc: fitz.Document, page_number_1based: int, dpi: int = 200) -> Image.Image:
    """Render a single page (1-based) to an RGB PIL image."""
    page = doc.load_page(page_number_1based - 1)  # lazy, no full-book load
    pix = page.get_pixmap(dpi=dpi)
    img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    pix = None  # release native buffer promptly
    return img
