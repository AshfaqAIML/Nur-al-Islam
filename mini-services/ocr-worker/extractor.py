"""Direct digital text extraction (no OCR spend on born-digital pages)."""
from __future__ import annotations

import fitz  # PyMuPDF

from schemas import OcrBlock, OcrLine


def embedded_text(page: fitz.Page) -> str:
    return page.get_text("text") or ""


def extract_digital(page: fitz.Page) -> dict:
    """Extract text + word-level blocks with coordinates from a digital page.

    Returns { text, blocks: OcrBlock[...] (confidence 1.0, engine-agnostic),
    char_count }. Raises nothing — empty pages yield empty text.
    """
    raw = page.get_text("dict")
    blocks: list[OcrBlock] = []
    parts: list[str] = []
    for b in raw.get("blocks", []):
        if b.get("type", 0) != 0:
            continue  # skip image blocks
        lines: list[OcrLine] = []
        for ln in b.get("lines", []):
            words = [s.get("text", "") for s in ln.get("spans", []) if s.get("text")]
            text = "".join(words).strip()
            if not text:
                continue
            x0, y0, x1, y1 = ln.get("bbox", [0, 0, 0, 0])
            lines.append(OcrLine(text=text, confidence=1.0, bbox=[x0, y0, x1, y1]))
            parts.append(text)
        if lines:
            xs0 = min(ln.bbox[0] for ln in lines)
            ys0 = min(ln.bbox[1] for ln in lines)
            xs1 = max(ln.bbox[2] for ln in lines)
            ys1 = max(ln.bbox[3] for ln in lines)
            blocks.append(
                OcrBlock(
                    text="\n".join(ln.text for ln in lines),
                    confidence=1.0,
                    bbox=[xs0, ys0, xs1, ys1],
                    lines=lines,
                )
            )
    text = "\n".join(parts)
    return {"text": text, "blocks": blocks, "char_count": len(text.strip())}
