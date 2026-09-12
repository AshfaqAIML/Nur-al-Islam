"""Primary OCR engine — EasyOCR (lazy import, cached Reader).

Urdu has no dedicated EasyOCR model: Urdu pages use the Arabic-script model
('ar'), which covers the shared script. Language hint mapping: ur→ar,
ar→ar, en→en, mixed/unknown→ar+en. Reader instances are cached per lang-set
(model load is expensive — never per page).
"""
from __future__ import annotations

import numpy as np
from PIL import Image

from config import WorkerConfig
from engines.base import EngineResult, EngineUnavailableError
from layout import blocks_from_lines
from schemas import OcrLine

_READERS: dict[tuple[str, ...], object] = {}


def _langs_for_hint(hint: str, configured: list[str]) -> list[str]:
    hint = (hint or "mixed").lower()
    if hint in ("ar", "ur"):
        return ["ar"]
    if hint == "en":
        return ["en"]
    return list(configured) if configured else ["ar", "en"]


class EasyOcrEngine:
    name = "easyocr"

    def __init__(self, config: WorkerConfig):
        self._config = config
        self.model_id = "craft_mlt_25k+arabic"
        self.model_version = config.easyocr_model_version

    def available(self) -> bool:
        try:
            import easyocr  # noqa: F401
            return True
        except ImportError:
            return False

    def _reader(self, langs: list[str]):
        import easyocr

        key = tuple(langs)
        if key not in _READERS:
            _READERS[key] = easyocr.Reader(list(langs), gpu=False, verbose=False)
        return _READERS[key]

    def recognize(self, image: Image.Image, lang_hint: str = "mixed") -> EngineResult:
        if not self.available():
            raise EngineUnavailableError("easyocr package not installed")
        langs = _langs_for_hint(lang_hint, self._config.easyocr_langs)
        reader = self._reader(langs)
        arr = np.array(image.convert("RGB"))
        raw = reader.readtext(arr, detail=1)
        lines: list[OcrLine] = []
        for bbox, text, conf in raw:
            text = (text or "").strip()
            if not text:
                continue
            xs = [p[0] for p in bbox]
            ys = [p[1] for p in bbox]
            lines.append(OcrLine(text=text, confidence=float(conf), bbox=[min(xs), min(ys), max(xs), max(ys)]))
        rtl = lang_hint != "en"
        # NOTE: the worker is Urdu/Arabic-first: "mixed" defaults to RTL.
        # lang_hint here is the *request* hint ("mixed" from the runner);
        # true per-line script detection happens downstream in normalize.py.
        # Passing lang_hint="en" is the only way to get LTR ordering.
        blocks = blocks_from_lines(lines, rtl=rtl)
        mean_conf = sum(ln.confidence for ln in lines) / len(lines) if lines else None
        text = "\n".join(b.text for b in blocks)
        return EngineResult(text=text, blocks=blocks, mean_confidence=mean_conf, model=self.model_id)
