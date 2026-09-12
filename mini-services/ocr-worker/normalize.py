"""Script utilities — language/script detection + search-safe normalization.

raw_text is ALWAYS stored verbatim. normalized_text applies only:
- Unicode NFC
- kashida (tahdeed U+0640) removal
- alef variant folding (أإآٱ → ا) — never touches ة/ه (meaning-bearing)
- optional tashkeel strip (diacritics U+064B–U+0652, U+0670) for the
  normalized variant; Quranic/diacritic text stays intact in raw_text.

Mirrors the spirit of src/lib/retrieval.ts detectLanguage (EN/UR/AR) so
stored `language` values line up with the RAG layer's expectations.
"""
from __future__ import annotations

import re
import unicodedata

ARABIC_RE = re.compile(r"[\u0600-\u06FF]")
# Urdu-specific codepoints (same set as src/lib/retrieval.ts detectLanguage)
_URDU_SPECIFIC = "[\u0679\u0688\u0691\u06BA\u06BE\u06C1\u06C3\u06D2\u06AF\u0686\u0698]"
URDU_SPECIFIC_RE = re.compile(_URDU_SPECIFIC)
TASHKEEL_RE = re.compile(r"[\u064B-\u0652\u0670]")
KASHIDA = "\u0640"
ALEF_FOLD = str.maketrans({"\u0623": "\u0627", "\u0625": "\u0627", "\u0622": "\u0627", "\u0671": "\u0627"})
# Urdu→Arabic codepoint folding, INDEX VARIANT ONLY (raw_text untouched).
# Rationale: vision OCR models trained on Arabic script emit Arabic forms
# (U+064A/U+0629, and U+0649 alef-maqsura for final-yeh) even for Urdu input
# typed as U+06CC/U+06C3 — verified against EasyOCR 1.7.2 on synthetic Urdu
# pages (2026-09-27). Folding both sides of the search comparison keeps Urdu
# queries matching regardless of input spelling. Display text is never folded.
URDU_FOLD = str.maketrans({"\u06CC": "\u064A", "\u06C3": "\u0629", "\u0649": "\u064A"})
LATIN_RE = re.compile(r"[A-Za-z]")


def detect_language(text: str) -> str:
    arabic = len(ARABIC_RE.findall(text))
    if arabic == 0:
        return "en" if LATIN_RE.search(text) else "unknown"
    urdu = len(URDU_SPECIFIC_RE.findall(text))
    latin = len(LATIN_RE.findall(text))
    if urdu > 0:
        return "mixed" if latin > 5 else "ur"
    if latin > 5:
        return "mixed"
    return "ar" if arabic > 2 else "unknown"


def detect_script(text: str) -> str:
    has_arab = bool(ARABIC_RE.search(text))
    has_latn = bool(LATIN_RE.search(text))
    if has_arab and has_latn:
        return "mixed"
    if has_arab:
        return "arab"
    if has_latn:
        return "latn"
    return "none"


def normalize_text(text: str, strip_tashkeel: bool = True) -> str:
    out = unicodedata.normalize("NFC", text)
    out = out.replace(KASHIDA, "")
    out = out.translate(ALEF_FOLD).translate(URDU_FOLD)
    if strip_tashkeel:
        out = TASHKEEL_RE.sub("", out)
    # collapse blank-heavy whitespace, keep line structure
    out = re.sub(r"[ \t]+", " ", out)
    out = re.sub(r"\n{3,}", "\n\n", out)
    return out.strip()


def fold_variants(text: str) -> str:
    """Offset-preserving fold for DETECTION (metadata regexes, markers).

    NFC + URDU_FOLD only (06CC/06C3/0649 -> Arabic forms) — all
    single-char->single-char, so match offsets stay valid against the
    original string. ALEF folding is deliberately EXCLUDED here: detection
    patterns use standard forms (e.g. U+0622 in AYA) and OCR emits them,
    so folding alefs would break more than it fixes. Alef folding lives
    only in normalize_text() (index variant). No stripping, no whitespace
    collapsing. Use before pattern matching on OCR output whose Urdu
    spellings vary.
    """
    return unicodedata.normalize("NFC", text).translate(URDU_FOLD)