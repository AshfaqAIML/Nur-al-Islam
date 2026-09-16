"""Indexing contract + end-to-end provenance on the two Phase 4 samples.

Chain asserted per page: Book → Jild → Page → text → language →
SearchDocument-shaped dict → full provenance. No server needed.

Ground truths below were verified against EasyOCR 1.7.2 output
(2026-09-27); all Urdu literals are \\u escapes (homoglyph-safe).
Known model gaps are asserted as None + documented, not hidden.
"""
from config import WorkerConfig
from conftest import sample
from engines import build_chain
from normalize import normalize_text
from renderer import open_pdf
from runner import process_page
from search_normalize import build_doc, search_text
from structure import chunk_page

# verified OCR spellings (Arabic forms emitted by the model)
SURA_BAQARA = "\u0627\u0644\u0628\u0642\u0631\u0629"      # البقرۃ
TIBYAN = "\u062A\u0628\u064A\u0627\u0646"                  # تبیان
RAZVI = "\u0631\u0636\u0648\u064A"                         # رضوی (final ۃ dropped by OCR)
SHARIF = "\u0634\u0631\u064A\u0641"                        # شریف
SUWAN = "\u0633\u0648\u0627\u0644"                         # سوال
JAWAB = "\u062C\u0648\u0627\u0628"                         # جواب
JILD = "\u062C\u0644\u062F"                                # جلد
BAB = "\u0628\u0627\u0628"                                 # باب
RUKU = "\u0631\u0643\u0648\u0639"                          # رکوع


def _process(pdf: str, page_no: int = 1):
    cfg = WorkerConfig()
    with open_pdf(sample(pdf)) as doc:
        return process_page(doc, page_no, cfg, build_chain(cfg), "job-4", "book-4", 4)


def _doc_for(pdf: str, page_id: str, title: str, route: str, lang: str) -> dict:
    res = _process(pdf)
    prov = {"bookId": "book-4", "volume": 4, "pageNumber": 1, "pdfPage": 1,
            "jobId": "job-4", "engine": res.engine, "model": res.model,
            "checksum": res.checksum, "language": res.language,
            "ocrConfidence": res.confidence, "verified": False,
            "textState": "raw+normalized",
            "signals": {**(res.signals or {}), "cues": res.metadata},
            **res.metadata}
    chunks = chunk_page(res.raw_text, {**prov, "pageId": page_id})
    assert chunks[0]["kind"] == "page"
    doc = build_doc(page_id, res.raw_text, title, route, lang, "book-4", {**prov, "pageId": page_id})
    return res, doc


def test_fatawa_sample_provenance_chain():
    res, d = _doc_for("fatawa_razvia_sample.pdf", "fr-p1", "Fatawa Razvia — vol. 4, p. 1",
                      "#/sources/book/fatawa-razvia", "AR")
    assert res.route == "SCANNED_PRINTED"
    # text (normalized level: OCR emits Arabic forms)
    norm = search_text(res.raw_text)
    for needle in (RAZVI, SHARIF, SUWAN, JAWAB, JILD, BAB):
        assert search_text(needle) in norm, needle
    assert "112" in res.raw_text and "113" in res.raw_text
    # metadata
    assert res.metadata["jild"] == 4
    assert res.metadata["masala"] == 112
    assert res.metadata["question"] is not None and res.metadata["answer"] is not None
    assert res.metadata["chapter"] is not None
    assert res.metadata["surah"] is None  # fiqh text: no surah cue
    # document shape + provenance completeness
    assert d["entityType"] == "BOOK_PAGE" and d["entityId"] == "fr-p1"
    assert d["bookId"] == "book-4" and d["weight"] == 1
    m = d["meta"]
    for k in ("volume", "pageNumber", "jobId", "engine", "checksum", "language",
              "textState", "verified", "ocrConfidence", "signals"):
        assert m[k] is not None, k
    assert (m["volume"], m["pageNumber"], m["jobId"]) == (4, 1, "job-4")
    assert m["masala"] == 112 and m["jild"] == 4
    assert d["bodySearch"] == search_text(d["body"])
    assert d["body"] == res.raw_text  # display = verbatim


def test_tibyan_sample_provenance_chain():
    res, d = _doc_for("tibyan_sample.pdf", "tb-p1", "Tibyan-ul-Quran — vol. 4, p. 1",
                      "#/sources/book/tibyan-ul-quran", "AR")
    assert res.route == "SCANNED_PRINTED"
    norm = search_text(res.raw_text)
    for needle in (TIBYAN, SURA_BAQARA, RUKU):
        assert search_text(needle) in norm, needle
    m = d["meta"]
    assert m["surah"] == SURA_BAQARA
    assert m["ayahStart"] == 2 and m["ayahEnd"] == 2
    assert m["ruku"] == 1
    # KNOWN MODEL GAP: Urdu peh (پ) misread as yeh → "پارہ" cue lost.
    # Unit level covers juz parsing; e2e pins current behavior.
    assert m["juz"] is None
    assert d["language"] == "AR"
    # display keeps diacritics; search variant folds them
    assert d["body"] == res.raw_text
    assert d["bodySearch"] == search_text(d["body"])
