"""Routing: DIGITAL never OCR'd, scans go to OCR, blanks skipped."""
import fitz

from config import WorkerConfig
from conftest import sample
from pdf_router import classify_page
from renderer import open_pdf


def _route(pdf_name: str) -> dict:
    cfg = WorkerConfig()
    with open_pdf(sample(pdf_name)) as doc:
        return classify_page(doc, 1, cfg)


def test_digital_english_routes_digital():
    r = _route("digital_en.pdf")
    assert r["route"] == "DIGITAL", r
    assert r["embedded_chars"] >= 50
    assert "wudu" in r["embedded_text"]


def test_digital_urdu_routes_digital():
    r = _route("digital_ur.pdf")
    assert r["route"] == "DIGITAL", r
    assert r["embedded_chars"] >= 20  # Urdu lines are short; threshold-independent check below
    assert len(r["embedded_text"].strip()) > 0


def test_scanned_pages_route_to_ocr():
    for name in ("scanned_urdu.pdf", "arabic_mixed.pdf", "poor_quality.pdf"):
        r = _route(name)
        assert r["route"] in ("SCANNED_PRINTED", "MIXED"), (name, r)
        assert r["embedded_chars"] < 50


def test_blank_page_skips_ocr_spend(tmp_path):
    pdf = str(tmp_path / "blank.pdf")
    doc = fitz.open()
    doc.new_page(width=595, height=842)
    doc.save(pdf)
    doc.close()
    cfg = WorkerConfig()
    with open_pdf(pdf) as d:
        r = classify_page(d, 1, cfg)
    assert r["route"] == "BLANK", r
