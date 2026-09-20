# Multi-Engine Real-Book Benchmark — Phase 11 Measurements

> 7 real pages (Fatawa Ridawiyyah vol4 + Tibyan-ul-Quran vol1) × EasyOCR +
> Tesseract × raw/restored = 28 scored records. Production unchanged.

## 1–2. Datasets & pages

- `eval/samples/real-fatawa/`: fz-p10 (dense Urdu mas'ala prose), fz-p100
  (2-col Arabic+Urdu + headings), fz-p400 (2-col + footnote refs), fz-p600
  (mas'ala headings + dates).
- `eval/samples/real-tibyan/`: tb-p100 (Urdu + Quranic verses + refs),
  tb-p200 (dense Urdu narrative), tb-p500 (hadith narrations + verses).
- GT: 57 human lines (`ground_truth/real-*/`, `source: human`, `partial`),
  bare-letter protocol, Quranic lines cross-checked. No Nastaliq (both books
  are Naskh — recorded gap), no tables, no bleed-through samples.

## 3–5. Engine versions & statuses

- EasyOCR 1.7.2 (craft_mlt_25k+arabic, CPU): MEASURED.
- Tesseract v5.4.0.20240606 + tessdata_best urd/ara/eng, `urd+ara+eng`,
  CPU: MEASURED (installed with user permission this phase).
- PaddleOCR 3.7.0: package installs; inference raises OneDNN
  `NotImplementedError` on this CPU → FAILED-attempt (infrastructure, not
  OCR quality). No Linux/GPU host available (no WSL distro, Docker pull not
  attempted — decision recorded, not assumed).
- Surya / Qaari-class: SKIPPED (absent / no wired model+license).

## 6–8. Urdu / Arabic / mixed (line match / coverage)

| Engine | All | Urdu (25 GT) | Mixed (32 GT) |
|---|---|---|---|
| EasyOCR raw | 9/57, cov 0.220 | 2/25 | 7/32 |
| EasyOCR restored | 10/57, cov 0.225 | 3/25 | 7/32 |
| Tesseract raw | 8/57, cov 0.310 | 4/25 | 4/32 |
| Tesseract restored | 5/57, cov 0.319 | 2/25 | 3/32 |

Pure-Arabic real pages: none (Quranic lines live inside mixed pages).

## 9. Preprocessing

Restored ≈ raw for both engines (EasyOCR +1 line, Tesseract −3 lines).
Deskew/contrast bundle earns no recommendation on these scans.

## 10–11. CER/WER, confidence

- wCER ≈ 0.85–1.0 across the board; confidences EasyOCR 0.19 vs Tesseract
  0.47 — but errors are equivalent, so Tesseract is WORSE calibrated
  (mid-range confidence ≠ mid-range accuracy). Never compare raw confidences
  across engines.
- Calibration bins: EasyOCR all in [0,0.3); Tesseract all in [0.3,0.6).
- Any-match rate: EasyOCR 5/7 pages, Tesseract 6/7.
- All 14 raw records triaged REVIEW → implied review rate ~100%.

## 12. Coverage

Folded GT-word recall: EasyOCR 0.22, Tesseract 0.31. Segmentation-independent;
the fairest single number for "how much content survives".

## 13–14. Runtime

EasyOCR ~50–165 s/page (model already warm in-process); Tesseract ~9–23
s/page (≈8× faster). Timings: Windows 11, py3.13.2, 12-thread CPU, no GPU.

## 15. Error examples (artifacts in run outputs/*/cases/)

Urdu glyph confusion (پ→ی, ہ→د), dropped word-finals, low-conf word salad,
segmentation splits, RTL line-order flips in 2-col layout; confident islands
(basmala 0.86–0.91). Quranic verses partially recovered, never clean.

## 16–17. Consensus (EasyOCR × Tesseract, raw)

Char agreement 0.22–0.33, word agreement 0.02–0.13 — engines disagree almost
everywhere, each winning different lines (fz-p100: easy 4/5 vs tess 2/5;
tb-p100: 0/10 vs 0/10). Disagreement does NOT cleanly predict error (both
wrong differently); agreement is too rare to exploit. Consensus-as-correction
is NOT viable for this pair; union strategies need per-line confidence work
that does not exist yet. `ConsensusEngine` (compare/align/score/select/flag)
is implemented, explainable, and refuses silent rewrites.

## 18. Infrastructure limitations

Windows CPU-only; no GPU; no WSL distro; Tesseract newly installed (user
dir); Paddle blocked on OneDNN; 150dpi fixtures (≈1MB total committed);
dpi 150 vs 300 identical (resolution not the bottleneck).
