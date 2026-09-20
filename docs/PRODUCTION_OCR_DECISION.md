# Production OCR Decision — Phase 10

> Evidence only — no winner score, no production change. Numbers in
> `docs/REAL_BOOK_OCR_BENCHMARK.md`; method in `docs/OCR_EVALUATION_LAB.md`.

1. **Native extraction for Fatawa?** Insufficient — the PDFs are pure scans
   (0 chars). Policy stands (prefer native *when present*); here OCR is
   mandatory, not optional.
2. **EasyOCR real Urdu?** Coverage 18–67% on 4 sampled pages — inadequate as
   a sole source; usable only behind human review (which correctly triggers).
3. **EasyOCR real Arabic?** Quranic islands recovered (0.86+ conf spots);
   overall weak; secondary criterion anyway.
4. **PaddleOCR real Urdu/Arabic?** Unmeasured (OneDNN CPU gap) — no claim.
5. **(Same as 4.)**
6. **Tesseract?** Unmeasured (no binary) — cheapest next data point.
7. **Specialist engine?** Most needed (Urdu primary), least available —
   Qaari-class evaluation requires a Linux/GPU environment + license check.
8. **Preprocessing?** Current bundle ≈ raw on real scans; no variant earns a
   recommendation. Stronger restoration is research, not config.
9. **Systematic errors?** Urdu-glyph confusion, dropped finals, segmentation
   splits, RTL flips, confident islands amid salad — see benchmark §5.
10. **Confidence/review?** Meaningful as a tripwire (4/4 caught, scores
    honestly low); threshold tuning needs more GT.
11. **Human review required?** ~100% of sampled real pages at current settings.
12. **Single engine sufficient?** No evidence for sufficiency.
13. **Consensus justified?** Unmeasurable yet; keep the module, install Tesseract.
14. **Change production OCR?** NO.

## Recommended next implementation (explicit, not silent)

1. Keep EasyOCR production route unchanged.
2. Install the Tesseract binary → rerun lab → enable the consensus
   experiment (EasyOCR×Tesseract disagreement as a review signal). [DONE Phase 11]
3. Stand up a Linux/GPU eval host: retry PaddleOCR 3.7 + Arabic/Urdu family,
   trial a Qaari-class Urdu model (record license/revision/prompt).
4. Source a Nastaliq printed book (the primary-metric script has zero
   real-page coverage) + footnotes/tables/degraded sets; grow GT line counts.
5. Only then: propose `EasyOCR → multi-engine routing` (or specialist) as a
   separate implementation phase with its own acceptance run.

Production stays exactly as-is until that phase passes.

---

## Phase 11 update — multi-engine real-book evidence (2026-09-27)

7 real pages × EasyOCR + Tesseract × raw/restored = 28 records.
Full numbers: `docs/MULTI_ENGINE_REAL_BOOK_BENCHMARK.md`.

- **Is EasyOCR still viable?** Unreviewed: no (coverage 0.22). Review-routed:
  yes — recovers real content (4/5 lines best page) with honest low
  confidence. Keep, never trust blindly.
- **Tesseract useful?** Yes as second opinion: higher coverage (0.31), 8×
  faster, wins different lines — but worse calibrated (0.47 conf at equal
  error). Not a replacement.
- **PaddleOCR?** Still unmeasurable (OneDNN CPU gap). No claim either way.
- **Specialist Urdu?** Biggest gap, still unavailable.
- **Consensus help?** Not via agreement (word agreement 0.02–0.13; both
  wrong differently). Union/confidence research is future work.
- **Strongest Arabic?** Neither reliably; EasyOCR has the only confident
  Quranic islands.
- **Preprocessing?** No recommendation (raw ≈ restored).
- **Auto-accept/review?** 0% / ~100% at current thresholds.
- **Difficult?** Dense Urdu, 2-col RTL, footnotes, small print.
- **Decision: production stays EasyOCR primary + Tesseract fallback.**
  Next (separate phase, when approved): Linux/GPU host for Paddle + Qaari
  trial, Nastaliq coverage, GT growth. No automatic switch.
