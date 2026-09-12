"""Chunking: page unit always, provenance inherited, quotations intact."""
from structure import build_chunk, chunk_page, find_quotations, split_paragraphs

PROV = {"bookId": "b", "volume": 4, "chapter": "باب الطہارۃ", "pageNumber": 112,
        "pdfPage": 120, "pageId": "p1", "jobId": "j1", "engine": "easyocr",
        "model": "m", "surah": None, "masala": 112}


def test_page_chunk_always_emitted_with_provenance():
    chunks = chunk_page("سوال: وضو؟\nجواب: مسح", PROV)
    assert len(chunks) == 1 and chunks[0]["kind"] == "page"
    for k in ("bookId", "volume", "chapter", "pageNumber", "pdfPage", "pageId", "jobId", "engine", "masala"):
        assert chunks[0][k] == PROV[k]
    assert chunks[0]["surah"] is None  # unknown stays None


def test_paragraph_children_inherit_provenance():
    text = "پہلا پیراگراف طویل متن ہے یہاں\n\nدوسرا پیراگراف بھی طویل متن ہے یہاں"
    chunks = chunk_page(text, PROV, min_paragraph_chars=10)
    assert chunks[0]["kind"] == "page"
    paras = [c for c in chunks if c["kind"] == "paragraph"]
    assert len(paras) == 2
    assert all(p["pageId"] == "p1" and p["masala"] == 112 for p in paras)
    assert paras[0]["start"] == 0 and paras[1]["start"] > paras[0]["end"]


def test_paragraphs_off_by_default():
    assert len(chunk_page("a\n\nb", PROV)) == 1


def test_quotation_spans_detected():
    qs = find_quotations('قال: "طلب العلم فریضۃ" پھر خاموش')
    assert len(qs) == 1 and "طلب العلم" in qs[0]["text"]
    assert find_quotations("no quotes here") == []


def test_split_paragraph_offsets():
    parts = split_paragraphs("one\n\ntwo\n\n\nthree")
    assert [p["text"] for p in parts] == ["one", "two", "three"]
    assert parts[1]["start"] > parts[0]["end"]
