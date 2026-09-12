"""Engine registry — primary + fallback chain from WorkerConfig.

PaddleOCR / PP-StructureV3 slot in here as another lazy engine module;
nothing outside this package names a provider. recognize_with_fallback()
tries each available engine in order, records warnings, and raises
EngineUnavailableError only when nothing can run.
"""
from __future__ import annotations

from PIL import Image

from config import WorkerConfig
from engines.base import EngineResult, EngineUnavailableError
from engines.easyocr_engine import EasyOcrEngine
from engines.htr import HtrStubEngine
from engines.tesseract_engine import TesseractEngine

REGISTRY = {
    "easyocr": EasyOcrEngine,
    "tesseract": TesseractEngine,
    "htr-stub": HtrStubEngine,
    # Future: "paddleocr": PaddleOcrEngine (PP-OCRv4/PP-StructureV3),
    #         "htr": RealHtrEngine — both behind lazy imports here.
}


def build_chain(config: WorkerConfig) -> list:
    names = [config.primary_engine, *config.fallback_engines]
    chain = []
    seen = set()
    for name in names:
        if name in seen:
            continue
        seen.add(name)
        cls = REGISTRY.get(name)
        if cls is None:
            continue  # unknown engine key → skip loudly via warning below
        chain.append(cls(config))
    return chain


def recognize_with_fallback(
    image: Image.Image, chain: list, lang_hint: str = "mixed"
) -> tuple[EngineResult, str, list[str]]:
    """Returns (result, engine_name_used, warnings)."""
    warnings: list[str] = []
    if not chain:
        raise EngineUnavailableError("empty OCR engine chain (check OCR_PRIMARY_ENGINE)")
    for engine in chain:
        if not engine.available():
            warnings.append(f"engine-unavailable:{engine.name}")
            continue
        try:
            result = engine.recognize(image, lang_hint=lang_hint)
            return result, engine.name, warnings
        except Exception as exc:  # noqa: BLE001 — fall through to next engine
            warnings.append(f"engine-failed:{engine.name}:{type(exc).__name__}")
    raise EngineUnavailableError(f"all OCR engines failed: {'; '.join(warnings)}")
