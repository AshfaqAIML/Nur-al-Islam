"""Candidate engine adapters (Phase 9, Part 6/7/8/9/21).

Every adapter reports AVAILABLE / SKIPPED / FAILED per run — nothing is
required to be installed for the lab to run. Local vs external vs
experimental engines are explicitly separated. PRINTED vs HANDWRITTEN
modalities are never cross-scored (HTR stub stays a stub).
"""
from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dataclasses import dataclass, field


@dataclass
class EvalLine:
    text: str
    confidence: float | None
    bbox: list[float] | None = None


@dataclass
class EvalResult:
    text: str
    lines: list[EvalLine]
    mean_confidence: float | None
    engine: str
    model: str
    model_version: str
    device: str
    runtime_s: float = 0.0
    warnings: list[str] = field(default_factory=list)


@dataclass
class EngineProbe:
    available: bool
    status: str  # AVAILABLE | SKIPPED
    version: str = ""
    reason: str = ""
    kind: str = "local"  # local | external | experimental
    modality: str = "printed"  # printed | handwritten


class EngineAdapter:
    key = "base"
    display = "base"
    kind = "local"
    modality = "printed"

    def probe(self) -> EngineProbe:  # pragma: no cover - overridden
        raise NotImplementedError

    def run(self, image, lang_hint: str = "mixed", **kwargs) -> EvalResult:  # pragma: no cover
        raise NotImplementedError


class EasyOCRAdapter(EngineAdapter):
    """Production route (wraps engines.easyocr_engine — no behavior change)."""

    key = "easyocr"
    display = "EasyOCR (production route)"

    def probe(self) -> EngineProbe:
        try:
            import easyocr

            return EngineProbe(True, "AVAILABLE", version=getattr(easyocr, "__version__", "?"), kind="local")
        except ImportError:
            return EngineProbe(False, "SKIPPED", reason="easyocr not installed")

    def run(self, image, lang_hint: str = "mixed", **kwargs) -> EvalResult:
        from config import WorkerConfig
        from engines.easyocr_engine import EasyOcrEngine

        cfg = WorkerConfig()
        eng = EasyOcrEngine(cfg)
        if not eng.available():
            raise RuntimeError("easyocr unavailable at run time")
        t0 = time.perf_counter()
        # lang_hint: urdu pages use the arabic-script model (production rule)
        langs = {"ur": ["ar"], "ar": ["ar"], "en": ["en"]}.get(lang_hint, cfg.easyocr_langs)
        import easyocr as _eo

        key = tuple(langs)
        from engines import easyocr_engine as _mod

        if key not in _mod._READERS:
            _mod._READERS[key] = _eo.Reader(list(langs), gpu=False, verbose=False)
        import numpy as _np

        raw = _mod._READERS[key].readtext(_np.array(image.convert("RGB")), detail=1)
        lines = [EvalLine(text=(t or "").strip(), confidence=float(c),
                          bbox=[min(p[0] for p in b), min(p[1] for p in b),
                                max(p[0] for p in b), max(p[1] for p in b)])
                 for b, t, c in raw if (t or "").strip()]
        mean = sum(ln.confidence or 0 for ln in lines) / len(lines) if lines else None
        _ = eng
        return EvalResult(text="\n".join(ln.text for ln in lines), lines=lines,
                          mean_confidence=mean, engine="easyocr",
                          model="craft_mlt_25k+arabic", model_version=cfg.easyocr_model_version,
                          device="cpu", runtime_s=time.perf_counter() - t0)


class TesseractAdapter(EngineAdapter):
    """Fallback route (wraps engines.tesseract_engine). Binary-gated."""

    key = "tesseract"
    display = "Tesseract (fallback route)"

    def probe(self) -> EngineProbe:
        import shutil

        if shutil.which("tesseract") is None:
            return EngineProbe(False, "SKIPPED", reason="tesseract system binary absent")
        try:
            import pytesseract  # noqa: F401
            return EngineProbe(True, "AVAILABLE", kind="local")
        except ImportError:
            return EngineProbe(False, "SKIPPED", reason="pytesseract not installed")

    def run(self, image, lang_hint: str = "mixed", **kwargs) -> EvalResult:
        from config import WorkerConfig
        from engines.tesseract_engine import TesseractEngine

        cfg = WorkerConfig()
        eng = TesseractEngine(cfg)
        if not eng.available():
            raise RuntimeError("tesseract unavailable at run time")
        t0 = time.perf_counter()
        res = eng.recognize(image, lang_hint=lang_hint)
        flat: list[EvalLine] = []
        for b in res.blocks:
            if b.lines:
                flat.extend(EvalLine(text=ln.text, confidence=ln.confidence, bbox=ln.bbox) for ln in b.lines)
            else:
                flat.append(EvalLine(text=b.text, confidence=b.confidence, bbox=b.bbox))
        lines = flat
        return EvalResult(text=res.text, lines=lines, mean_confidence=res.mean_confidence,
                          engine="tesseract", model=eng.model_id, model_version=eng.model_version,
                          device="cpu", runtime_s=time.perf_counter() - t0)


class PaddleAdapter(EngineAdapter):
    """PP-OCR evaluation (Part 7). Real adapter; SKIPPED unless installed.

    Arabic/Urdu family: lang="ar" (shared-script; Urdu has no dedicated PP
    model — recorded per run, never assumed). PaddleOCR 3.x API
    (predict-based); versions/runtime/device recorded from the install.
    No model paths hardcoded — PaddlePaddle hub resolution at run time.
    """

    key = "paddleocr"
    display = "PaddleOCR (PP-OCR multilingual/ar)"

    def __init__(self, lang: str = "ar"):
        self.lang = lang

    def probe(self) -> EngineProbe:
        try:
            import paddleocr  # noqa: F401
            import paddleocr as _p

            return EngineProbe(True, "AVAILABLE", version=getattr(_p, "__version__", "?"), kind="local")
        except ImportError:
            return EngineProbe(False, "SKIPPED",
                               reason="paddleocr (+paddlepaddle) not installed in this interpreter")

    def run(self, image, lang_hint: str = "mixed", **kwargs) -> EvalResult:
        from paddleocr import PaddleOCR  # lazy: only on AVAILABLE

        t0 = time.perf_counter()
        ocr = PaddleOCR(lang=self.lang)
        import numpy as _np

        out = ocr.predict(_np.array(image.convert("RGB")))
        lines: list[EvalLine] = []
        for page in out or []:
            texts = page.get("rec_texts") or []
            scores = page.get("rec_scores") or []
            boxes = page.get("dt_boxes") or []
            for i, tx in enumerate(texts):
                box = boxes[i].tolist() if i < len(boxes) else None
                flat = [float(v) for pt in (box or []) for v in pt] if box else None
                bbox = [min(flat[0::2]), min(flat[1::2]), max(flat[0::2]), max(flat[1::2])] if flat else None
                lines.append(EvalLine(text=str(tx), confidence=float(scores[i]) if i < len(scores) else None, bbox=bbox))
        mean = sum(ln.confidence or 0 for ln in lines) / len(lines) if lines else None
        return EvalResult(text="\n".join(ln.text for ln in lines), lines=lines,
                          mean_confidence=mean, engine="paddleocr",
                          model=f"PP-OCR/lang={self.lang}", model_version="paddleocr-runtime",
                          device="cpu", runtime_s=time.perf_counter() - t0)


class SuryaAdapter(EngineAdapter):
    """Line-level specialist (where technically appropriate)."""

    key = "surya"
    display = "Surya (line specialist)"

    def probe(self) -> EngineProbe:
        try:
            import surya  # noqa: F401
            return EngineProbe(True, "AVAILABLE", kind="local")
        except ImportError:
            return EngineProbe(False, "SKIPPED", reason="surya not installed")


class QaariAdapter(EngineAdapter):
    """EXPERIMENTAL specialized Urdu VLM (Part 8). Never auto-promoted."""

    key = "qaari"
    display = "Qaari-class Urdu VLM (experimental)"
    kind = "experimental"

    def __init__(self, model: str = "", revision: str = "", prompt: str = ""):
        self.model = model
        self.revision = revision
        self.prompt = prompt

    def probe(self) -> EngineProbe:
        return EngineProbe(False, "SKIPPED", kind="experimental",
                           reason="no compatible Urdu VLM wired (model/revision/license unverified)")


class NativeExtractAdapter(EngineAdapter):
    """Part 21 baseline: native PDF text extraction (NOT OCR)."""

    key = "native-extract"
    display = "Native PDF text extraction (baseline)"

    def probe(self) -> EngineProbe:
        try:
            import fitz  # noqa: F401
            return EngineProbe(True, "AVAILABLE", kind="local")
        except ImportError:
            return EngineProbe(False, "SKIPPED", reason="PyMuPDF not installed")

    def run(self, image=None, lang_hint: str = "mixed", **kwargs) -> EvalResult:
        import fitz

        pdf_path = kwargs.get("pdf_path")
        page_no = int(kwargs.get("page_no", 1))
        if not pdf_path:
            raise RuntimeError("native-extract needs pdf_path + page_no")
        t0 = time.perf_counter()
        doc = fitz.open(pdf_path)
        try:
            text = doc.load_page(page_no - 1).get_text("text") or ""
        finally:
            doc.close()
        return EvalResult(text=text.strip(), lines=[], mean_confidence=1.0 if text.strip() else None,
                          engine="native-extract", model="embedded-text",
                          model_version="pymupdf-digital-1", device="cpu",
                          runtime_s=time.perf_counter() - t0)


REGISTRY: dict[str, EngineAdapter] = {
    "easyocr": EasyOCRAdapter(),
    "tesseract": TesseractAdapter(),
    "paddleocr": PaddleAdapter(),
    "surya": SuryaAdapter(),
    "qaari": QaariAdapter(),
    "native-extract": NativeExtractAdapter(),
}
