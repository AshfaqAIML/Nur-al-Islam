"""Metadata extractors: cues only — unknowns stay None, nothing invented."""
from metadata import detect_chapter, detect_fatawa, detect_section, detect_tafsir, page_metadata
from normalize import fold_variants  # expectations fold identically (06C3/0629-proof)


def test_fatawa_markers():
    text = "فتاویٰ رضویہ شریف\nجلد 4\nمسئلہ نمبر 112\nسوال: وضو؟\nجواب: مسح فرض ہے"
    f = detect_fatawa(text)
    assert f["jild"] == 4
    assert f["masala"] == 112
    assert f["question"] is not None and f["answer"] is not None
    assert f["question"][1] <= f["answer"][0]


def test_fatawa_absent_stays_none():
    f = detect_fatawa("یہ ایک عام صفحہ ہے جس میں کوئی نشان نہیں")
    assert f == {"jild": None, "masala": None, "question": None, "answer": None}


def test_tafsir_markers():
    text = "سورۃ البقرۃ\nآیت 3 الی 4\nپارہ 1\nركوع 1"
    t = detect_tafsir(text)
    assert t["surah"] == fold_variants("البقرۃ")
    assert t["ayahStart"] == 3 and t["ayahEnd"] == 4
    assert t["juz"] == 1 and t["ruku"] == 1


def test_tafsir_absent_stays_none():
    t = detect_tafsir("plain english page about wudu")
    assert all(v is None for v in t.values())


def test_arabic_indic_digits():
    t = detect_tafsir("پارہ ۱۲")
    assert t["juz"] == 12


def test_chapter_section():
    assert detect_chapter("باب الطہارۃ") == fold_variants("الطہارۃ")
    assert detect_chapter("no heading here at all") is None
    assert detect_section("مسئلہ نمبر 112") is not None
    assert detect_section("plain text") is None


def test_combined_pass():
    m = page_metadata("جلد 4\nباب الطہارۃ")
    assert m["jild"] == 4
    assert m["chapter"] == fold_variants("الطہارۃ")
    assert m["surah"] is None and m["masala"] is None
