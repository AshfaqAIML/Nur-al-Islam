"""HTR abstraction — handwriting has NO text path in this system.

is_handwritten_candidate() is a cheap pre-OCR heuristic (stroke
irregularity proxy via connected-component aspect-ratio spread). Anything
flagged must be routed to NEEDS_REVIEW; recognize() always raises
HTRNotImplementedError so handwritten material can never be presented as
OCR output. A future HTR model plugs in behind this same interface.
"""
from __future__ import annotations

import cv2
import numpy as np
from PIL import Image

from config import WorkerConfig
from engines.base import EngineResult, HTRNotImplementedError


def is_handwritten_candidate(image: Image.Image) -> bool:
    """Heuristic only: high spread of component aspect ratios + low OCR-style
    regularity suggests handwriting. Tuned conservatively (better to OCR a
    handwritten page than to refuse a printed one — the flag only routes to
    review when combined with low engine confidence)."""
    gray = np.array(image.convert("L"))
    _, bw = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    contours, _ = cv2.findContours(bw, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    ratios: list[float] = []
    for c in contours:
        x, y, w, h = cv2.boundingRect(c)
        if w * h < 60 or h < 8:
            continue
        ratios.append(max(w, h) / max(1, min(w, h)))
        if len(ratios) > 2000:
            break
    if len(ratios) < 40:
        return False
    arr = np.array(ratios)
    # printed text: tight aspect distribution; handwriting: wide spread
    return bool(arr.std() > 2.2 and (arr > 5.0).mean() > 0.12)


class HtrStubEngine:
    """Placeholder behind the HTR interface. Never returns text."""

    name = "htr-stub"

    def __init__(self, config: WorkerConfig):
        self._config = config
        self.model_id = "htr-stub/none"
        self.model_version = "htr-stub-0"

    def available(self) -> bool:
        return False  # no HTR model wired yet — intentional

    def recognize(self, image: Image.Image, lang_hint: str = "mixed") -> EngineResult:
        raise HTRNotImplementedError(
            "No HTR model configured. Route handwritten pages to NEEDS_REVIEW for human transcription."
        )
