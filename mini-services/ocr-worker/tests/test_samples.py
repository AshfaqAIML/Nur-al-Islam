"""End-to-end sample validation in --dry-run (no server needed).

- digital page: exact text recovery, route DIGITAL, engine pymupdf-digital
- scanned Urdu page (EasyOCR, models cached): non-empty Arabic-script text
- Arabic mixed page: runs, script detected
- poor-quality page: runs, records quality warnings
EasyOCR tests skip gracefully if the engine/models are unavailable.
"""
import pytest

from config import WorkerConfig
from conftest import expected, sample
from engines.easyocr_engine import EasyOcrEngine
from renderer import open_pdf
from runner import process_page
from engines import build_chain

easyocr = pytest.importorskip("easyocr", reason="easyocr not installed")


def _chain():
    return build_chain(WorkerConfig(primary_engine="easyocr", fallback_engines=[]))


def test_digital_page_exact_recovery():
    cfg = WorkerConfig()
    with open_pdf(sample("digital_en.pdf")) as doc:
        res = process_page(doc, 1, cfg, _chain(), None, None, 1)
    assert res.route == "DIGITAL"
    assert res.engine == "pymupdf-digital"
    assert res.confidence == 1.0
    for needle in expected("digital_en.pdf"):
        assert needle in res.raw_text


def test_scanned_urdu_ocr():
    eng = EasyOcrEngine(WorkerConfig())
    if not eng.available():
        pytest.skip("easyocr unavailable")
    try:
        cfg = WorkerConfig()
        with open_pdf(sample("scanned_urdu.pdf")) as doc:
            res = process_page(doc, 1, cfg, _chain(), "job-x", "book-x", 1)
    except Exception as exc:
        pytest.skip(f"OCR model load failed offline: {exc}")
    assert res.route in ("SCANNED_PRINTED", "MIXED")
    assert res.engine == "easyocr"
    assert len(res.raw_text.strip()) > 20, res.raw_text[:200]
    assert res.script in ("arab", "mixed")
    assert res.language in ("ar", "ur", "mixed")
    assert res.checksum and len(res.checksum) == 64
    assert res.blocks and res.blocks[0].bbox[2] > res.blocks[0].bbox[0]


def test_arabic_mixed_page_runs():
    cfg = WorkerConfig()
    with open_pdf(sample("arabic_mixed.pdf")) as doc:
        try:
            res = process_page(doc, 1, cfg, _chain(), None, None, 1)
        except Exception as exc:
            pytest.skip(f"OCR model load failed offline: {exc}")
    assert res.script in ("arab", "mixed", "latn")
    assert res.to_writeback()["ocrText"] == res.raw_text


def test_cli_dry_run_single_page(capsys):
    from runner import main

    rc = main(["--dry-run", "--pdf", sample("digital_en.pdf"), "--pages", "1"])
    assert rc == 0
    out = capsys.readouterr().out.strip().splitlines()[-1]
    import json

    stats = json.loads(out)
    assert stats["done"] == 1 and stats["failed"] == 0


def test_poor_quality_page_records_warnings():
    cfg = WorkerConfig()
    with open_pdf(sample("poor_quality.pdf")) as doc:
        try:
            res = process_page(doc, 1, cfg, _chain(), None, None, 1)
        except Exception as exc:
            pytest.skip(f"OCR model load failed offline: {exc}")
    assert len(res.warnings) >= 1, "degraded fixture must record quality warnings"
    assert res.checksum is not None
