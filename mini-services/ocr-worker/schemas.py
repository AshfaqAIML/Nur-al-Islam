"""Result schemas — one PageResult per page (spec § OCR RESULT).

Coordinates are image pixels (x0,y0,x1,y1, top-left origin) plus the rendered
image size for normalization. to_writeback() produces the exact payload for
PATCH /api/admin/pages { action: "ocr" } — small JSON, never PDF bytes.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass
class OcrLine:
    text: str
    confidence: float
    bbox: list[float]  # [x0, y0, x1, y1] in image pixels


@dataclass
class OcrBlock:
    text: str
    confidence: float
    bbox: list[float]
    lines: list[OcrLine] = field(default_factory=list)


@dataclass
class PageResult:
    job_id: str | None
    book_id: str | None
    volume: int
    page_number: int
    route: str               # DIGITAL | SCANNED_PRINTED | MIXED | BLANK | HANDWRITTEN
    raw_text: str            # verbatim — never translated/corrected
    normalized_text: str     # search-friendly variant (see normalize.py)
    confidence: float | None
    language: str            # ar | ur | en | mixed | unknown
    script: str              # arab | latn | mixed | none
    image_width: int
    image_height: int
    blocks: list[OcrBlock] = field(default_factory=list)
    engine: str = "unknown"  # registry key that produced the text
    model: str = ""          # model file / identifier
    model_version: str = ""  # package + model pin from config
    checksum: str | None = None  # sha256 of the rendered page image
    warnings: list[str] = field(default_factory=list)

    @property
    def lines(self) -> list[OcrLine]:
        out: list[OcrLine] = []
        for b in self.blocks:
            # NOTE: `is not None` (not truthiness) — an explicitly empty line
            # list must stay empty, not synthesize a None-confidence line.
            out.extend(b.lines if b.lines is not None else [OcrLine(text=b.text, confidence=b.confidence, bbox=b.bbox)])
        return out

    def to_dict(self) -> dict:
        d = asdict(self)
        d["line_count"] = len(self.lines)
        d["char_count"] = len(self.raw_text)
        return d

    def to_writeback(self) -> dict:
        """Payload for PATCH /api/admin/pages { action: "ocr" }."""
        return {
            "ocrText": self.raw_text,
            "ocrConfidence": self.confidence,
            "language": self.language,
            "engine": f"{self.engine}/{self.model_version}" if self.model_version else self.engine,
            "checksum": self.checksum,
        }
