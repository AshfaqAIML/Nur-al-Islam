# Real-Book OCR Benchmark — Phase 10 Measurements

> 4 real pages, human line-sampled GT (32 lines, bare-letter protocol),
> EasyOCR 1.7.2/ar CPU. No production changes. Artifacts under
> `mini-services/ocr-worker/eval/outputs/` (gitignored).

## 1. Sources (Part 1 gate: PASSED)

- Fatawa: `Islam24x7/Books/Fatah Ridawiyyah/fatawa_ridawiyyah_vol_04.pdf`
  (753 pp, 55.7 MB). Tibyan: `Books/Quran/tibyan-ul-quran-vol-01.pdf`
  (1053 pp, 36 MB, +13-vol manifest with sha256).
- CRITICAL: both are pure scans — 0 embedded chars on sampled pages.
  "Computerized" ≠ digital text layer here.

## 2. Sample (no mass ingest)

| ID | Source | Content | Categories |
|---|---|---|---|
| real-fatawa/fz-p100 | vol4 p100 | 2-col Arabic+Urdu, headings | mixed, headings |
| real-fatawa/fz-p400 | vol4 p400 | 2-col + footnote refs | mixed, footnotes |
| real-tibyan/tb-p200 | vol1 p200 | dense Urdu narrative | urdu (Naskh) |
| real-tibyan/tb-p100 | vol1 p100 | Urdu + Quranic verses + refs | mixed, quran |

Fixtures committed at 150dpi (~1MB total). Absent (documented, not forced):
Nastaliq (both books are Naskh), 3+ columns, tables, bleed-through, severe
degradation. GT: `eval/ground_truth/real-*/` (`source: human`, `partial`).

## 3. Digital baseline (Part 3): native = 0 chars → OCR REQUIRED

`NativeExtractAdapter` on the real Fatawa PDF returns empty. Policy outcome:
native stays preferred *if* text exists; here it doesn't, so OCR fallback
engages. OCR cannot "degrade" what isn't there.

## 4. EasyOCR on real pages (line-level, folded matching)

| Page | Match | Coverage | wCER | Conf | Verdict | s |
|---|---|---|---|---|---|---|
| fz-p100 | 4/5 | 0.667 | 1.159 | 0.25 | REVIEW | 55–79 |
| fz-p400 | 2/8 | 0.184 | 0.848 | 0.21 | REVIEW | 50–68 |
| tb-p200 | 1/9 | 0.257 | 0.875 | 0.13 | REVIEW | 118–140 |
| tb-p100 | 0/10 | 0.275 | 1.000 | 0.23 | REVIEW | 118–165 |

Restored ≈ raw (fz-p400 0.86 vs 0.85; tb-p100 +1 match). dpi 150 vs 300:
identical match (resolution not the bottleneck). Determinism: identical CER
across repeats. Calibration (synthetic): monotonic bins.

## 5. Error analysis (preserved per case)

Urdu glyph confusion (پ→ی, ہ→د), dropped word-finals, low-conf word salad,
segmentation splits, RTL line-order flips in 2-col layout; correct islands
(basmala at 0.86–0.91 conf). Quranic lines partially recovered; footnote
numerals survive better than prose.

## 6. Other engines

tesseract SKIPPED (no binary) · paddleocr SKIPPED main-env + FAILED venv
attempt (OneDNN `NotImplementedError`, CPU kernel gap — infrastructure, not
OCR quality) · surya SKIPPED (absent) · qaari SKIPPED experimental ·
consensus unmeasurable (<2 engines) · HTR untouched (no handwritten samples).

## 7. Review mechanism

All 4 real pages triaged REVIEW with honestly low confidences — thresholds
work as a safety net. Implied review rate on such scans: ~100% at current
settings; tuning needs a larger GT set (`review_signal_stats` ready).
