"""Fallback OCR engine — Tesseract (system binary + data files required).

Default langs `urd+ara+eng` (configurable). When the binary or pytesseract
is absent, available() is False and the chain moves on — never fatal.
"""
from __future__ import annotations

import shutil

from PIL import Image

from config import WorkerConfig
from engines.base import EngineResult, EngineUnavailableError
from layout import blocks_from_lines
from schemas import OcrLine


class TesseractEngine:
    name = "tesseract"

    def __init__(self, config: WorkerConfig):
        self._config = config
        self.model_id = f"tessdata:{config.tesseract_langs}"
        self.model_version = "tesseract-system"

    def available(self) -> bool:
        if shutil.which(self._config.tesseract_cmd) is None:
            return False
        try:
            import pytesseract  # noqa: F401
            return True
        except ImportError:
            return False

    def recognize(self, image: Image.Image, lang_hint: str = "mixed") -> EngineResult:
        if not self.available():
            raise EngineUnavailableError("tesseract binary or pytesseract missing")
        import pytesseract

        data = pytesseract.image_to_data(
            image, lang=self._config.tesseract_langs, output_type=pytesseract.Output.DICT
        )
        words: dict[tuple[int, int, int], list[str]] = {}
        word_conf: dict[tuple[int, int, int], list[float]] = {}
        word_box: dict[tuple[int, int, int], list[list[int]]] = {}
        n = len(data.get("text", []))
        for i in range(n):
            word = (data["text"][i] or "").strip()
            try:
                conf = float(data["conf"][i])
            except (ValueError, TypeError):
                conf = -1.0
            if not word or conf < 0:
                continue
            key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
            words.setdefault(key, []).append(word)
            word_conf.setdefault(key, []).append(conf)
            word_box.setdefault(key, []).append(
                [data["left"][i], data["top"][i], data["left"][i] + data["width"][i], data["top"][i] + data["height"][i]]
            )
        out: list[OcrLine] = []
        for key, wds in words.items():
            boxes = word_box[key]
            bbox = [min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes)]
            out.append(
                OcrLine(
                    text=" ".join(wds),
                    confidence=sum(word_conf[key]) / len(word_conf[key]) / 100.0,
                    bbox=[float(v) for v in bbox],
                )
            )
        blocks = blocks_from_lines(out, rtl=True)
        mean_conf = sum(ln.confidence for ln in out) / len(out) if out else None
        return EngineResult(text="\n".join(b.text for b in blocks), blocks=blocks, mean_confidence=mean_conf, model=self.model_id)
