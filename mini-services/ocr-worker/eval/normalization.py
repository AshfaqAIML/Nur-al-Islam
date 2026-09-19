"""Evaluation normalization modes (Phase 9, Part 12).

Reuses the production normalizer (normalize.normalize_text) — never
duplicates its rules. Ground truth is NEVER altered: modes apply to COPIES
used only for the normalized comparison. Both raw and normalized scores are
always retained side by side; normalization effects are reported as their
own breakdown (diacritic-only and unicode-only deltas), never hidden.
"""
from __future__ import annotations

import os
import re
import sys
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from normalize import TASHKEEL_RE, normalize_text  # noqa: E402  (reuse, not duplication)
from metrics import cer  # noqa: E402  (eval package; see eval/tests/conftest.py)

NORMALIZATION_RULES = [
    "NFC unicode normalization",
    "kashida (U+0640) removal",
    "alef variants (U+0623/U+0625/U+0622/U+0671) -> U+0627",
    "Urdu forms U+06CC/U+06C3/U+0649 -> Arabic U+064A/U+0629",
    "tashkeel strip U+064B-U+0652/U+0670 (normalized mode only)",
    "whitespace collapse (blank runs, 3+ newlines)",
]


def normalize_for_eval(text: str) -> str:
    """Index-equivalent form (what the search pipeline compares)."""
    return normalize_text(text, strip_tashkeel=True)


def strip_diacritics_only(text: str) -> str:
    """Diacritic strip isolated: measures how much error is tashkeel-only."""
    return TASHKEEL_RE.sub("", unicodedata.normalize("NFC", text))


def unicode_only(text: str) -> str:
    """NFC only: isolates encoding-form differences from real errors."""
    return unicodedata.normalize("NFC", text)


def word_count(text: str) -> int:
    return len(text.split())


def diacritic_density(text: str) -> float:
    """Fraction of combining/diacritic chars — context for diacritic deltas."""
    if not text:
        return 0.0
    marks = sum(1 for c in text if unicodedata.combining(c) or "\u064B" <= c <= "\u0652" or c == "\u0670")
    return marks / len(text)


def normalization_breakdown(ref: str, hyp: str) -> dict:
    """How much of the raw gap each normalization layer explains."""
    raw = cer(ref, hyp)["cer"]
    uni = cer(unicode_only(ref), unicode_only(hyp))["cer"]
    dia = cer(strip_diacritics_only(ref), strip_diacritics_only(hyp))["cer"]
    ful = cer(normalize_for_eval(ref), normalize_for_eval(hyp))["cer"]
    return {
        "raw_cer": raw,
        "unicode_only_cer": uni,
        "diacritics_stripped_cer": dia,
        "normalized_cer": ful,
        "explained_by_unicode": max(0.0, raw - uni),
        "explained_by_diacritics": max(0.0, uni - dia),
        "explained_by_folding": max(0.0, dia - ful),
        "residual_cer": ful,
        "ref_diacritic_density": diacritic_density(ref),
    }
