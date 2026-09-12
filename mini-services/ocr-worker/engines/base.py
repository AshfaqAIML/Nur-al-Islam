"""OCR engine abstraction — no caller hardwires a provider.

Each engine implements OcrEngine (name/model_id/model_version/available/
recognize). The registry chain (primary + fallbacks from WorkerConfig) is
resolved in engines/__init__.py. HTR lives here too as an explicit
abstraction: it can FLAG handwriting candidates but has no text path —
OCR and HTR are never confused.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from PIL import Image

from schemas import OcrBlock


@dataclass
class EngineResult:
    text: str
    blocks: list[OcrBlock]
    mean_confidence: float | None
    model: str = ""
    warnings: list[str] | None = None


class OcrEngine(Protocol):
    name: str
    model_id: str
    model_version: str

    def available(self) -> bool:
        """False → skipped with a recorded warning (never fatal)."""
        ...

    def recognize(self, image: Image.Image, lang_hint: str = "mixed") -> EngineResult:
        ...


class EngineUnavailableError(RuntimeError):
    pass


class HTRNotImplementedError(RuntimeError):
    """Raised whenever handwritten material reaches the HTR stub.

    The page must then be routed to NEEDS_REVIEW — HTR output must never
    be presented as OCR text.
    """
