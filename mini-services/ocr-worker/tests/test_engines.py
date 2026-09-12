"""Engine registry: no hardwired provider, graceful fallback, HTR separation."""
import pytest
from PIL import Image

from config import WorkerConfig
from engines import build_chain, recognize_with_fallback
from engines.base import EngineResult, EngineUnavailableError, HTRNotImplementedError
from engines.htr import HtrStubEngine, is_handwritten_candidate
from engines.tesseract_engine import TesseractEngine
from conftest import sample
from renderer import open_pdf, render_page


class FakeEngine:
    name = "fake"
    model_id = "fake-1"
    model_version = "fake-0"

    def __init__(self, available=True, fail=False):
        self._available = available
        self._fail = fail

    def available(self):
        return self._available

    def recognize(self, image, lang_hint="mixed"):
        if self._fail:
            raise RuntimeError("boom")
        return EngineResult(text="ok", blocks=[], mean_confidence=0.9, model="fake-1")


def _img() -> Image.Image:
    with open_pdf(sample("scanned_urdu.pdf")) as doc:
        return render_page(doc, 1, dpi=150)


def test_chain_skips_unavailable_and_failed_engines():
    img = _img()
    res, used, warnings = recognize_with_fallback(
        img, [FakeEngine(available=False), FakeEngine(fail=True), FakeEngine()], "ur"
    )
    assert used == "fake" and res.text == "ok"
    assert any("engine-unavailable" in w for w in warnings)
    assert any("engine-failed" in w for w in warnings)


def test_empty_chain_and_total_failure_raise():
    img = _img()
    with pytest.raises(EngineUnavailableError):
        recognize_with_fallback(img, [], "ur")
    with pytest.raises(EngineUnavailableError):
        recognize_with_fallback(img, [FakeEngine(available=False)], "ur")


def test_tesseract_degrades_without_binary():
    eng = TesseractEngine(WorkerConfig())
    assert eng.available() is False  # no tesseract binary in this env
    with pytest.raises(EngineUnavailableError):
        eng.recognize(_img())


def test_htr_stub_never_returns_text():
    eng = HtrStubEngine(WorkerConfig())
    assert eng.available() is False
    with pytest.raises(HTRNotImplementedError):
        eng.recognize(_img())


def test_handwriting_heuristic_returns_bool():
    assert isinstance(is_handwritten_candidate(_img()), bool)


def test_unknown_engine_key_ignored_in_chain():
    cfg = WorkerConfig(primary_engine="nope-not-real", fallback_engines=[])
    assert build_chain(cfg) == []
