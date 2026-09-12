"""Verification signals flag uncertainty; text is never corrected."""
from config import WorkerConfig
from schemas import OcrLine, PageResult
from verify import lexicon_score, token_overlap, unicode_anomaly_ratio, verify_page


def _res(text="test", conf=0.9, route="SCANNED_PRINTED", language="en", script="latn", lines=None) -> PageResult:
    from schemas import OcrBlock

    lns = lines if lines is not None else [OcrLine(text=text, confidence=conf, bbox=[0, 0, 100, 20])]
    return PageResult(job_id=None, book_id=None, volume=1, page_number=1, route=route,
                      raw_text=text, normalized_text=text, confidence=conf, language=language,
                      script=script, image_width=100, image_height=100,
                      blocks=[OcrBlock(text=text, confidence=conf, bbox=[0, 0, 100, 20], lines=lns)])


def test_clean_page_verdict_ok():
    s = verify_page(_res("washing the face and the arms", 0.95), WorkerConfig())
    assert s["verdict"] == "OK" and s["reasons"] == []


def test_low_confidence_flagged():
    s = verify_page(_res("gibberish " * 60, 0.2, lines=[
        OcrLine(text="x", confidence=0.2, bbox=[0, 0, 50, 20]),
        OcrLine(text="y", confidence=0.3, bbox=[0, 25, 50, 45]),
    ]), WorkerConfig())
    assert s["verdict"] == "REVIEW"
    assert "low-mean-confidence" in s["reasons"]


def test_handwritten_always_review():
    s = verify_page(_res("", None, route="HANDWRITTEN", language="unknown", script="none", lines=[]), WorkerConfig())
    assert s["verdict"] == "REVIEW" and "handwritten-needs-transcription" in s["reasons"]


def test_engine_disagreement_on_mixed():
    r = _res("totally different words here", 0.9, route="MIXED")
    s = verify_page(r, WorkerConfig(), embedded_text="باب الوضوء مسح فرض سنت")
    assert s["engineDisagreement"] is not None and s["engineDisagreement"] > 0.5
    assert "embedded-text-disagreement" in s["reasons"]


def test_unicode_anomalies_flagged():
    s = verify_page(_res("normal text  with private use " * 10, 0.9), WorkerConfig())
    assert s["unicodeAnomalies"] > 0.02
    assert "unicode-anomalies" in s["reasons"]


def test_lexicon_weak_garbage_flagged():
    garbage = " ".join([f"zxq{k}qv" for k in range(60)])
    assert lexicon_score(garbage, "en") == 0.0
    s = verify_page(_res(garbage, 0.9), WorkerConfig())
    assert "lexicon-signal-weak" in s["reasons"]


def test_token_overlap():
    assert token_overlap("a b c", "a b c") == 1.0
    assert token_overlap("a b", "x y z") == 0.0
    assert token_overlap("", "x") == 0.0
