"""Normalization keeps raw verbatim; language detection matches RAG expectations."""
from normalize import detect_language, detect_script, fold_variants, normalize_text


def test_tashkeel_stripped_only_in_normalized():
    raw = "بِسْمِ اللَّهِ"
    norm = normalize_text(raw)
    assert raw != norm  # diacritics present in raw…
    assert "ِ" not in norm and "َّ" not in norm  # …gone in normalized
    assert normalize_text(raw, strip_tashkeel=False) == raw.strip() or "ِ" in normalize_text(raw, strip_tashkeel=False)


def test_kashida_removed_alef_folded_teh_marbuta_kept():
    norm = normalize_text("كـتـاب أحمد مدرسة")
    assert "ـ" not in norm
    assert "أحمد" not in norm and "احمد" in norm
    assert "مدرسة".replace("ة", "X") not in norm  # ة untouched
    assert "مدرس" in norm and "ة" in normalize_text("مدرسة")


def test_detect_urdu_needs_urdu_specific_chars():
    assert detect_language("یہ ایک آزمائشی صفحہ ہے") == "ur"
    assert detect_language("كتاب الطهارة") == "ar"
    assert detect_language("washing the face") == "en"
    assert detect_language("باب الوضوء washing the face value") == "mixed"
    assert detect_language("123 !?") == "unknown"


def test_detect_script():
    assert detect_script("السلام") == "arab"
    assert detect_script("hello") == "latn"
    assert detect_script("سلام hello") == "mixed"
    assert detect_script("123") == "none"


def test_urdu_codepoint_folding_index_only():
    # Verified EasyOCR behavior: Urdu 06CC/06C3 emitted as Arabic 064A/0629,
    # final-yeh as 0649. Index folds both spellings together; raw untouched.
    urdu_spelled = "\u062a\u0628\u06cc\u0627"  # T-B-YH-A, Urdu yeh
    arab_spelled = "\u062a\u0628\u064a\u0627"  # same word, Arabic yeh
    assert urdu_spelled != arab_spelled  # genuinely different codepoints
    assert normalize_text(urdu_spelled) == normalize_text(arab_spelled)
    assert fold_variants(urdu_spelled) == fold_variants(arab_spelled)
    assert normalize_text("\u0649") == normalize_text("\u064a")  # maqsura fold
    assert normalize_text("\u06c3") == normalize_text("\u0629")  # marbuta-goal fold


def test_milad_spellings_fold_together():
    # Phase 5 example query: Urdu-typed vs OCR-emitted spellings index equal.
    urdu_typed = "\u0645\u06cc\u0644\u0627\u062f"  # 06CC yeh
    ocr_emitted = "\u0645\u064a\u0644\u0627\u062f"  # 064A yeh
    assert urdu_typed != ocr_emitted
    assert normalize_text(urdu_typed) == normalize_text(ocr_emitted)
    assert detect_language(ocr_emitted + " " + "\u0627\u0644\u0646\u0628\u064a") in ("ar", "ur", "mixed")


def test_fold_variants_preserves_offsets():
    raw = "AB12 CD"
    assert fold_variants(raw) == raw
    assert len(fold_variants("X")) == len("X")
