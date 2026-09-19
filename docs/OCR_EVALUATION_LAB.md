# OCR Evaluation Lab — Phase 9 Architecture

> Measure, don't assume. Production OCR (`engines/`) is UNCHANGED — the lab
> only reads through adapters. No engine is promoted by this phase.

## 1. Current production OCR (audited, not modified)

- Primary: EasyOCR 1.7.2 (`engines/easyocr_engine.py`), langs `ar,en`
  (Urdu → Arabic-script model; no dedicated Urdu model), Reader cached per
  lang-set, CPU, models `craft_mlt_25k + arabic` (pre-cached).
- Fallback: Tesseract (`urd+ara+eng`), binary-gated (absent here → clean skip).
- PaddleOCR/PP-StructureV3: registry slot only. HTR: stub (flags, never texts).
- Preprocessing (`preprocess.py`): adaptive, self-gating steps (deskew, crop,
  background/deshadow, denoise, CLAHE contrast, mild deblur; binarize and
  dewarp OFF by default), copy-on-write, applied-steps logged.
- Output: lines w/ bboxes + confidences, mean confidence, engine/model pins.
- Known limits (measured, see reports): Urdu raw CER ~0.55 on clean synthetic
  Naskh (Arabic-script model reading Urdu); 06CC/06C3/0649 emitted as Arabic
  forms (folded at index); peh→yeh misreads; dropped word-final heh; no
  Nastaliq-specific handling; confidence uncalibrated (but monotonic).

## 2. Lab layout (`mini-services/ocr-worker/eval/`)

`samples/{urdu,arabic,mixed,degraded,difficult,footnotes,headings,quran}/`
(incremental — any subset runs), `ground_truth/`, `outputs/` + `reports/`
(gitignored artifacts), `configs/`, `tests/`. `NUR_EVAL_DIR` points at an
external collection so real PDFs/pages never enter git. In-repo fixtures are
11 small synthetic PNGs (448KB) + authored GT (`source: fixture`).

## 3. Ground truth format

`{sample_id, language, script, source: human|fixture, source_note,
lines: [{text, bbox|null}], reading_order?}`. Validated
(`validate_ground_truth`); model output is rejected as a source. Reference
text = lines joined (optionally in reading order).

## 4. Engine adapters (`engines_eval.py`, registry `REGISTRY`)

| Key | Kind | Status here |
|---|---|---|
| easyocr | local (production route) | AVAILABLE, measured |
| tesseract | local (fallback) | SKIPPED — no system binary |
| paddleocr | local (PP-OCR ar) | SKIPPED in main env (not installed); venv attempt: installs but inference raises OneDNN `NotImplementedError` on this CPU → FAILED-attempt, recorded |
| surya | local | SKIPPED — not installed |
| qaari | experimental VLM | SKIPPED — no wired model/revision/license |
| native-extract | local baseline (Part 21) | AVAILABLE (PDF digital-text path) |

Every run records AVAILABLE/SKIPPED/FAILED per engine. HTR modality is
separate: adapters declare `printed|handwritten`; cross-scoring refused.

## 5. Preprocessing variants (`preprocess_variants.py`)

`raw` (always the baseline) + deskew/contrast/deshadow/denoise/background/
deblur/restored (= production bundle). Exact flag sets recorded per test;
more ≠ better (measured: restored ≈ raw on clean fixtures).

## 6. Metrics

- `metrics.py`: CER/WER + insertions/deletions/substitutions (own Levenshtein,
  verified against known values). Layout (`layout_metrics.py`: IoU matching,
  precision/recall/F1, Kendall-tau order distance) reported SEPARATELY.
- Normalization (`normalization.py`, reuses worker rules): every score kept
  as RAW + NORMALIZED, plus a breakdown attributing the gap to unicode-only,
  diacritics-only, and folding layers. GT never altered.
- Language (`language.py`): ur/ar/mixed always split (Urdu authoritative);
  combined accompanies, never replaces.
- Calibration (`calibration.py`): confidence bins vs measured CER (monotonic
  on fixtures — confidence tracks error but is NOT a calibrated probability).
- Review signals: production `verify.verdict` vs CER>0.05 → FP/FN/review
  rate/miss rate for threshold tuning.
- Resources (`resources.py`): load vs per-page seconds, pages/min, CPU RSS
  (psutil), GPU iff CUDA, full env fingerprint per run.
- Domain (`domain.py`): per-term hit-rate by engine (error analysis, NOT
  truth). Consensus: pair agreement across engines (experimental).
- Error analysis (`errors.py`): substitution/deletion/insertion/segmentation/
  dot-diacritic/RTL-order classes + saved artifacts (image, GT, hypothesis).

## 7. Reports (`reports.py`)

`results.json` (full records) + `results.csv` (flat) + `report.md` (per-engine
cuts by language/category/variant + calibration + skipped list). No winner
score — ever.

## 8. Decision gate (measured 2026-09-27, fixtures, CPU)

1. EasyOCR: ar CER 0.23→0.03 norm; ur 0.55→0.50; mixed 0.69; WER 0.6–0.88;
   ~1.9–7 s/page; deterministic across repeats.
2. PaddleOCR: not measurable here (OneDNN kernel gap on this CPU).
3. Tesseract: not measurable (no binary).
4. Surya: not installed. 5. Qaari-class: no wired model.
6. Urdu: EasyOCR-only data (0.55 raw). 7. Arabic: EasyOCR 0.23/0.03.
8. Degraded: covered by fixtures; full degraded cuts need real pages.
9. Preprocessing: no meaningful gain on clean fixtures; test on real scans.
10. Multi-engine verification: consensus module ready; needs ≥2 engines.
11. Review rate: threshold-dependent — run `review_signal_stats` on real pages.
12. Next: real Fatawa/Tibyan pages via NUR_EVAL_DIR; install Tesseract binary;
    retry Paddle on Linux/GPU; Nastaliq font fixtures; footnotes/headings GT.

**Recommendation: DO NOT change production OCR.** Evidence is insufficient
(single-engine data, synthetic fixtures). EasyOCR stays; rerun this lab on
real pages before any switch.
