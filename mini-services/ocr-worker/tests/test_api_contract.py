"""Writeback contract: payloads match PATCH /api/admin/pages {action:'ocr'}."""
from runner import RESUMABLE, parse_range
from schemas import PageResult


def _result(**kw) -> PageResult:
    base = dict(job_id="j", book_id="b", volume=1, page_number=1, route="SCANNED_PRINTED",
                raw_text="متن", normalized_text="متن", confidence=0.8, language="ur",
                script="arab", image_width=100, image_height=100, engine="easyocr",
                model="craft", model_version="v1", checksum="abc")
    base.update(kw)
    return PageResult(**base)


def test_writeback_payload_shape():
    wb = _result().to_writeback()
    assert set(wb) == {"ocrText", "ocrConfidence", "language", "engine", "checksum"}
    assert wb["ocrText"] == "متن"
    assert wb["ocrConfidence"] == 0.8
    assert "easyocr" in wb["engine"]
    assert wb["checksum"] == "abc"


def test_writeback_never_carries_binary():
    wb = _result().to_writeback()
    for v in wb.values():
        assert not isinstance(v, (bytes, bytearray))


def test_resumable_set_matches_server():
    # server: PENDING | QUEUED | FAILED resumable; OCR_DONE | INDEXED | NEEDS_REVIEW skipped
    assert RESUMABLE == {"PENDING", "QUEUED", "FAILED"}


def test_parse_range():
    assert parse_range(None, 800) == list(range(1, 801))
    assert parse_range("1-3,5", 800) == [1, 2, 3, 5]
    assert parse_range("0,799-999", 800) == [799, 800]  # clamped
