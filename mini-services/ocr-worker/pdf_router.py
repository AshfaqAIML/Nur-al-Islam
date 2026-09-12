"""PDF/page routing — DIGITAL vs SCANNED_PRINTED vs MIXED vs BLANK.

- DIGITAL: enough embedded text → extract directly, never OCR.
- SCANNED_PRINTED: image-only page → render → preprocess → OCR.
- MIXED: some embedded text but below threshold (e.g. partial layer) AND
  image content → OCR primary, embedded text kept as a cross-check warning.
- BLANK: negligible ink → skip OCR spend, store empty text.
- HANDWRITTEN is NOT decided here (no reliable cheap signal pre-OCR);
  engines/htr.py flags handwriting candidates post-render and the runner
  routes those to NEEDS_REVIEW. OCR and HTR are never confused: the HTR
  stub has no recognize() path into OCR results.
"""
from __future__ import annotations

import fitz  # PyMuPDF
import numpy as np
from PIL import Image

from config import WorkerConfig
from extractor import embedded_text
from renderer import render_page


def ink_coverage(image: Image.Image) -> float:
    """Fraction of dark pixels on a thumbnail — cheap content detector."""
    gray = image.convert("L").resize((200, 200))
    arr = np.asarray(gray, dtype=np.float32) / 255.0
    return float((arr < 0.5).mean())


def classify_page(
    doc: fitz.Document,
    page_number_1based: int,
    config: WorkerConfig,
) -> dict:
    page = doc.load_page(page_number_1based - 1)
    text = embedded_text(page)
    chars = len(text.strip())
    thumb = render_page(doc, page_number_1based, dpi=config.thumb_dpi)
    coverage = ink_coverage(thumb)
    del thumb  # thumbnail was routing-only; full render happens later per page

    if coverage < config.blank_ink_coverage and chars < config.digital_min_chars:
        return {"route": "BLANK", "embedded_chars": chars, "ink_coverage": coverage, "embedded_text": ""}
    if chars >= config.digital_min_chars:
        return {"route": "DIGITAL", "embedded_chars": chars, "ink_coverage": coverage, "embedded_text": text}
    if chars > 0:
        return {"route": "MIXED", "embedded_chars": chars, "ink_coverage": coverage, "embedded_text": text}
    return {"route": "SCANNED_PRINTED", "embedded_chars": chars, "ink_coverage": coverage, "embedded_text": ""}
