"""Verification signals — flag uncertain content, never correct it.

Signals per page (all stored in BookPage.signals JSON):
- ocr_confidence: mean engine confidence (null for digital/blank)
- low_conf_ratio: fraction of lines below 0.5 confidence
- engine_disagreement: for MIXED pages, embedded-vs-OCR token overlap
  (low overlap = the scan disagrees with the text layer → review)
- script_confidence: 1.0 if detected script matches lang_hint family
- unicode_anomalies: ratio of suspicious chars (private-use, unassigned
  in Arabic block, excessive combining marks, lone surrogates)
- lexicon_score: fraction of tokens containing a function word from a
  small curated list (ur/ar/en) — very low scores suggest garbage OCR
- layout_flags: overlapping line bboxes, lines out of reading order
- structural_flags: empty blocks, single giant line, zero lines with text

verdict(): OK | REVIEW — REVIEW routes to NEEDS_REVIEW. Thresholds live in
config (conservative defaults: better a false review flag than silent garbage).
"""
from __future__ import annotations

import re
import unicodedata

from config import WorkerConfig
from schemas import OcrLine, PageResult

# tiny function-word lists — presence signals "real language", absence proves nothing
LEXICON = {
    "ur": {"کا", "کی", "کے", "میں", "سے", "نے", "اور", "ہے", "ہیں", "تھا", "کو", "پر", "یہ", "وہ"},
    "ar": {"من", "في", "على", "إلى", "أن", "التي", "الذي", "هذا", "هذه", "كان", "مع", "عن", "ما", "لا"},
    "en": {"the", "of", "and", "to", "in", "is", "for", "on", "with", "as", "by", "are"},
}

_SUSPICIOUS_RES = [
    re.compile(r"[\uE000-\uF8FF\U000F0000-\U000FFFFF]"),  # private use
    re.compile(r"[\u0600-\u0605\u06DD-\u06DF\u06E9]"),    # unassigned/format oddities in Arabic block
]


def token_overlap(a: str, b: str) -> float:
    ta = set(re.findall(r"[\w\u0600-\u06FF]+", a.lower()))
    tb = set(re.findall(r"[\w\u0600-\u06FF]+", b.lower()))
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / max(len(ta), len(tb))


def lexicon_score(text: str, language: str) -> float | None:
    words = re.findall(r"[\w\u0600-\u06FF]+", text.lower())
    if not words:
        return None
    bag = LEXICON.get(language)
    if not bag:
        return None
    hits = sum(1 for w in words if w in bag)
    return hits / max(1, len(words))


def unicode_anomaly_ratio(text: str) -> float:
    if not text:
        return 0.0
    bad = 0
    combining_run = 0
    for ch in text:
        if any(rx.match(ch) for rx in _SUSPICIOUS_RES):
            bad += 1
        if unicodedata.combining(ch):
            combining_run += 1
            if combining_run > 3:
                bad += 1
        else:
            combining_run = 0
    return bad / len(text)


def layout_flags(lines: list[OcrLine]) -> list[str]:
    flags: list[str] = []
    if not lines:
        return ["no-lines"]
    # overlap: two lines whose bboxes intersect substantially
    for i in range(len(lines)):
        for j in range(i + 1, len(lines)):
            a, b = lines[i].bbox, lines[j].bbox
            if a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]:
                flags.append("overlapping-lines")
                break
        if flags:
            break
    heights = [(ln.bbox[3] - ln.bbox[1]) for ln in lines if ln.bbox[3] > ln.bbox[1]]
    if heights and (max(heights) / max(1, min(heights))) > 8:
        flags.append("line-height-spread")
    return flags


def structural_flags(result: PageResult) -> list[str]:
    flags: list[str] = []
    if result.raw_text and not result.blocks:
        flags.append("text-without-blocks")
    if len(result.raw_text) > 2000 and len(result.lines) <= 1:
        flags.append("single-giant-line")
    if result.route in ("SCANNED_PRINTED", "MIXED") and not result.raw_text.strip():
        flags.append("empty-ocr-output")
    return flags


def verify_page(
    result: PageResult,
    config: WorkerConfig,
    embedded_text: str = "",
    lang_hint: str = "mixed",
) -> dict:
    lines = result.lines
    low = [ln for ln in lines if ln.confidence < 0.5]
    signals: dict = {
        "ocrConfidence": result.confidence,
        "lowConfRatio": (len(low) / len(lines)) if lines else None,
        "engineDisagreement": None,
        "scriptConfidence": None,
        "unicodeAnomalies": round(unicode_anomaly_ratio(result.raw_text), 4),
        "lexiconScore": lexicon_score(result.raw_text, result.language),
        "layoutFlags": layout_flags(lines),
        "structuralFlags": structural_flags(result),
    }
    if result.route == "MIXED" and embedded_text.strip() and result.raw_text.strip():
        overlap = token_overlap(embedded_text, result.raw_text)
        signals["engineDisagreement"] = round(1.0 - overlap, 3)
    if result.language != "unknown":
        fam_ok = (result.script in ("arab", "mixed") and result.language in ("ar", "ur", "mixed")) or (
            result.script in ("latn", "mixed") and result.language in ("en", "mixed")
        )
        signals["scriptConfidence"] = 1.0 if fam_ok else 0.0

    reasons: list[str] = []
    if result.route == "HANDWRITTEN":
        reasons.append("handwritten-needs-transcription")
    if result.confidence is not None and result.confidence < 0.45:
        reasons.append("low-mean-confidence")
    if (signals["lowConfRatio"] or 0) > 0.4:
        reasons.append("many-low-confidence-lines")
    if (signals["engineDisagreement"] or 0) > 0.7:
        reasons.append("embedded-text-disagreement")
    if signals["unicodeAnomalies"] > 0.02:
        reasons.append("unicode-anomalies")
    lex = signals["lexiconScore"]
    if lex is not None and lex < 0.02 and len(result.raw_text) > 200:
        reasons.append("lexicon-signal-weak")
    if "overlapping-lines" in signals["layoutFlags"] or "empty-ocr-output" in signals["structuralFlags"]:
        reasons.append("layout-or-structure")
    signals["verdict"] = "REVIEW" if reasons else "OK"
    signals["reasons"] = reasons
    _ = config
    return signals
