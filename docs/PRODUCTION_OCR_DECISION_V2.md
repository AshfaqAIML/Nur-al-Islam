# Production OCR Decision V2 — Phase 12 (formal recommendation)

> Decision/review only. No production change, no mass ingest, no BookPage
> rewrites. Evidence: 7 real pages × EasyOCR + Tesseract × raw/restored =
> 28 records, 57 human GT lines. Method: `docs/OCR_EVALUATION_LAB.md`.

## 1. Executive conclusion

KEEP EasyOCR primary + Tesseract fallback. Neither engine earns promotion;
neither earns removal. The measured gap is coverage depth (Tesseract slightly
ahead) versus honesty and Quranic islands (EasyOCR). The correct near-term
investment is review-routed ingestion with both engines' outputs preserved —
not an engine switch. Threshold rule (§18): NOT MET — no alternative shows
meaningful, repeatable, deployable improvement.

## 2. Real-book evidence

- Fatawa Ridawiyyah vol4 (753pp, 55.7MB) + Tibyan-ul-Quran vol1 (1053pp,
  36MB): pure scans, 0 embedded chars (native extraction NOT viable).
- 7 sampled pages (4 Fatawa: dense mas'ala prose, 2-col Arabic+Urdu,
  headings, footnote refs; 3 Tibyan: dense narrative, Quranic verses+refs,
  hadith narrations). Fixtures committed at 150dpi (~1MB).
- 57 GT lines, human-transcribed, bare-letter protocol, Quranic lines
  cross-checked, line-sampled (`partial`) with matched-CER + coverage metrics.
- Runtimes: EasyOCR 43–165 s/page; Tesseract 5–23 s/page (≈8× faster).
  Windows 11, Python 3.13.2, 12-thread CPU, no GPU. Deterministic repeats.

## 3. Engine-by-engine measurements

| Engine | Verdict | Match/57 | Coverage | Conf | s/page |
|---|---|---|---|---|---|
| EasyOCR 1.7.2/ar CPU | MEASURED | 9–10 | 0.06–0.67 | 0.13–0.27 | 43–165 |
| Tesseract 5.4.0 urd+ara+eng CPU | MEASURED | 8 | 0.12–0.55 | 0.38–0.54 | 5–23 |
| PaddleOCR 3.7.0 | FAILED_INFRA (OneDNN CPU gap) | — | — | — | — |
| Qaari-class / Surya | SKIPPED (absent/unwired) | — | — | — | — |

wCER ≈ 0.85–1.0 everywhere; restored ≈ raw (±1 line noise) for both engines.

## 4. Urdu analysis (primary criterion)

Urdu GT (25 lines): EasyOCR 2–3, Tesseract 2–4 matched. Tesseract leads
slightly on Urdu prose; both inadequate unreviewed. Urdu-specific failure
modes: peh→yeh, heh→dal, dropped finals, Nastaliq untested (both books are
Naskh — primary-script gap stands).

## 5. Arabic analysis (secondary)

Quranic islands partially recovered (basmala 0.86–0.91 spots, EasyOCR);
mixed pages carry most Arabic. No pure-Arabic real page sampled (synthetic
fixture: EasyOCR 0.23/0.03 raw/norm CER). Neither engine reliable on verses.

## 6. Fatawa analysis

29 GT lines: EasyOCR 7, Tesseract 6 matched. Best page fz-p100 (4/5 EasyOCR).
2-col RTL flips + footnote numerals + small print dominate errors. Union
upper bound per page barely exceeds best-single (e.g. [4,5], [2,3]).

## 7. Tibyan analysis

28 GT lines: 2 + 2 matched. Dense narrative worst (tb-p100: 0/10 both).
Verse refs (surah:ayah) survive better than prose. No engine leads.

## 8. Preprocessing findings

No variant earns recommendation: restored vs raw within ±1 line for both
engines across 14 paired runs. Keep the safe adaptive bundle (harmless);
stronger restoration is research, not config. dpi 150 vs 300 identical.

## 9. Consensus findings

Char agreement 0.22–0.33, word 0.02–0.13; per-page union bounds ≈ best
single. Agreement does not predict correctness (both wrong differently);
disagreement is near-universal, so it cannot route either. Consensus-as-
correction: NOT viable for this pair. `ConsensusEngine` stays as documented
research code; union strategies need confidence work that doesn't exist.

## 10. Confidence findings

Both engines trip REVIEW on 100% of real pages (correct). EasyOCR scores
honestly low (0.13–0.27); Tesseract scores mid (0.38–0.54) at equal error —
worse calibrated, never comparable across engines. Confidence is a tripwire,
not a probability; Tesseract's must be down-weighted in any future routing.

## 11. Operational considerations

EasyOCR: 200MB+ models cached, slow, honest. Tesseract: 15MB binary +
tessdata_best, fast, overconfident. Paddle: needs Linux/GPU host. Specialist:
needs license + host. All local/CPU-viable except Paddle. Reproducible via
`eval/bench.py` + pinned versions. Memory unremarkable (CPU RSS, no GPU).

## 12. Recommended architecture

REVIEW-ROUTED DUAL CAPTURE (no winner, no consensus correction):
PAGE → quality/language analysis → EasyOCR (primary record) + Tesseract
(fast second opinion, always run — it's 8× faster) → store BOTH outputs per
page (separate fields, never merged) → verification signals on each →
human review where required (effectively 100% of real scans today) →
verified text promotes to index. Disagreement between stored outputs becomes
a review-priority signal (not a correction). Single-engine pages (e.g. cost
reasons) default to EasyOCR for its honest confidence.

## 13. Reasons

Coverage maxima differ per page (union bound > single on 5/7 pages);
Tesseract speed makes dual capture cheap; honest-confidence EasyOCR keeps
triage meaningful; no silent rewriting anywhere; every claim above is a
measured number in §3–§10.

## 14. Risks

Dual storage doubles page-row width (text columns) — SQLite-fine at current
scale; review labor dominates cost, not compute; Tesseract overconfidence
must not leak into routing (down-weight by policy); GT set is small (57
lines) — all rates have wide intervals.

## 15. Unresolved uncertainties

Nastaliq (zero coverage), tables/bleed/severe degradation, PaddleOCR quality,
specialist-Urdu quality, Tesseract calibration mapping, threshold tuning
beyond n=7,Footnote-heavy recall, GPU-speed economics.

## 16. Exact next implementation steps

Separate approval-gated phase: (1) add `ocrTextSecondary` (+engine/conf) to
BookPage; (2) worker runs Tesseract after EasyOCR, stores both; (3) review UI
shows both with diff highlight; (4) index from verified-or-primary per
current policy; (5) benchmark gate re-run (this lab, +10 GT lines) must show
union coverage gain before any routing change. See
`docs/PRODUCTION_OCR_IMPLEMENTATION_PLAN.md`.
