"""Heuristic metadata extractors — cues only, never invention.

Every extractor returns None when its pattern is absent. Unknown values
stay NULL through the whole pipeline (BookPage/SearchDocument.meta).
Covers: chapter/section headings, Tafsir (surah/ayah range/juz/ruku),
Fatawa (jild/mas'ala/question/answer spans).

Detection input is folded first (fold_variants: NFC + alef/Urdu folds,
all 1:1, offsets preserved) so Urdu spelling variants (06CC/064A/0649,
06C3/0629) match regardless of typed-vs-OCR forms. All Arabic literals in
this file are explicit \\u escapes (homoglyph-safe: no lookalike glyphs).
"""
from __future__ import annotations

import re

from normalize import fold_variants

# Arabic-Indic + Extended Arabic-Indic digits → int
_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")


def _num(raw: str) -> int | None:
    try:
        return int(raw.translate(_DIGITS))
    except ValueError:
        return None


def _first_int(pattern: str, text: str) -> int | None:
    m = re.search(pattern, text)
    return _num(m.group(1)) if m else None


_BAB = "\u0628\u0627\u0628"          # باب
_FASL = "\u0641\u0635\u0644"          # فصل
_KITAB = "\u0643\u062A\u0627\u0628"    # کتاب
_MASALA = "\u0645\u0633\u0626\u0644"    # مسئل (final char optional: OCR drops it)
_MASALA_T = "\u0645\u0633\u0623\u0644"  # مسأل
_JILD = "\u062C\u0644\u062F"          # جلد
_MUJALLAD = "\u0627\u0644\u0645\u062C\u0644\u062F"  # المجلد
_SUWAN = "\u0633\u0648\u0627\u0644"    # سوال
_JAWAB = "\u062C\u0648\u0627\u0628"    # جواب
_SURA = "\u0633\u0648\u0631"          # سور
_AYA = "\u0622\u064A\u062A"           # آیت (064A: folded 06CC/0649 match here)
_AYAT = "\u0622\u064A\u0627\u062A"     # آیات
_PARA = "\u067E\u0627\u0631\u06C1"     # پارہ (peh form; misread OCR stays None)
_JUZ = "\u0627\u0644\u062C\u0632\u0621"  # الجزء
_JUZ2 = "\u062C\u0632\u0621"          # جزء
_RUKU = "\u0631\u0643\u0648\u0639"      # رکوع
_NUM = "([0-9\u0660-\u0669\u06F0-\u06F9]+)"
_NMBR = "(?:\u0646\u0645\u0628\u0631\\s*)?"  # نمبر + space
_TEH = "[\u0629\u06C3]"               # ة/ۃ
_YEH = "[\u064A\u06CC\u0649]"         # ي/ی/ى
# NMBR marker words accept reh|lam final (U+0631|U+0644): verified OCR
# confusion pair on Urdu scans (EasyOCR 1.7.2). Numbers stay required.
_RANGE_SEP = "(?:[-\u2013]|\u0627\u0644\u064A|\u0627\u0644\u0649|\u062A\u0627|\u0625\u0644\u0649)"

# --- generic structure -------------------------------------------------

_CHAPTER_RES = [
    "(?m)^\\s*(?:" + _BAB + "|" + _FASL + "|" + _KITAB + ")\\s+(.+?)\\s*$",
    r"(?m)^\s*(?:Chapter|CHAPTER)\s+(\d+.*)\s*$",
    r"(?m)^\s*(?:Section|SECTION)\s+(\d+.*)\s*$",
]
_SECTION_RES = [
    "(?m)^\\s*(?:" + "\u0645\u0633\u0626\u0644\u06C1" + "|\u0645\u0628\u062D\u062B" + ")\\s*(?:" + "\u0646\u0645\u0628[\u0631\u0644]" + "\\s*)?(.+?)\\s*$",
]


def detect_chapter(text: str) -> str | None:
    text = fold_variants(text)
    for rx in _CHAPTER_RES:
        m = re.search(rx, text)
        if m and 0 < len(m.group(1).strip()) <= 120:
            return m.group(1).strip()
    return None


def detect_section(text: str) -> str | None:
    text = fold_variants(text)
    for rx in _SECTION_RES:
        m = re.search(rx, text)
        if m and 0 < len(m.group(1).strip()) <= 160:
            return m.group(1).strip()
    return None


# --- Tafsir ------------------------------------------------------------

def detect_tafsir(text: str) -> dict:
    """Surah/ayah-range/juz/ruku cues. All None unless matched."""
    text = fold_variants(text)
    out: dict = {"surah": None, "ayahStart": None, "ayahEnd": None, "juz": None, "ruku": None}
    m = re.search(_SURA + _TEH + r"\s+([^\s\u060C,;:()\[\]0-9\u0660-\u0669\u06F0-\u06F9]{2,40})", text)
    if m:
        out["surah"] = m.group(1).strip()
    m = re.search("(?:%s|%s|%s%s)%s\\s*%s(?:\\s*%s\\s*%s)?" % (_AYA, _AYAT, "\u0627\u0644\u0622\u064A" + _TEH, "", r"\s*", _NUM, _RANGE_SEP, _NUM), text)
    if m:
        out["ayahStart"] = _num(m.group(1))
        out["ayahEnd"] = _num(m.group(2)) if m.group(2) else out["ayahStart"]
    out["juz"] = _first_int("(?:%s|%s|%s)\\s*(?:%s)?%s" % (_PARA, _JUZ, _JUZ2, "\u0646\u0645\u0628[\u0631\u0644]", _NUM), text)
    out["ruku"] = _first_int(_RUKU + "\\s*(?:\u0646\u0645\u0628\u0631\\s*)?" + _NUM, text)
    return out


# --- Fatawa ------------------------------------------------------------

def detect_fatawa(text: str) -> dict:
    """Jild/mas'ala/question-answer spans. All None unless matched."""
    text = fold_variants(text)
    out: dict = {
        "jild": None, "masala": None,
        "question": None, "answer": None,  # char offsets of سوال/جواب markers
    }
    out["jild"] = _first_int("(?:%s|%s)\\s*(?:%s\\s*)?%s" % (_JILD, _MUJALLAD, "\u0646\u0645\u0628[\u0631\u0644]", _NUM), text)
    # مسئل + optional final char: OCR sometimes drops the word-final heh
    # ("مسئلہ" → "مسئل"); the required nearby number keeps this precise.
    m = re.search("(?:%s\\S?|%s%s|%s%s)\\s*(?:%s\\s*)?%s" % (_MASALA, _MASALA_T, _TEH, "\u0627\u0644\u0645\u0633\u0623\u0644", _TEH, "\u0646\u0645\u0628[\u0631\u0644]", _NUM), text)
    if m:
        out["masala"] = _num(m.group(1))
    q = re.search(_SUWAN + "\\s*[:\u061F?]?", text)
    a = re.search(_JAWAB + "\\s*[:\u061F?]?", text)
    if q and a and a.start() > q.start():
        out["question"] = [q.end(), a.start()]
        out["answer"] = [a.end(), len(text)]
    return out


def page_metadata(text: str) -> dict:
    """Combined pass — one dict, None-heavy by design."""
    meta: dict = {"chapter": detect_chapter(text), "section": detect_section(text)}
    meta.update(detect_tafsir(text))
    meta.update(detect_fatawa(text))
    return meta
