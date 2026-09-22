# Dual-Capture OCR — Phase 13 Deliverable

> Review-routed second opinions, not auto-correction. Primary OCR untouched,
> nothing merged, nothing auto-verified. Production routing unchanged
> (EasyOCR primary); dual capture is configuration-gated (default: review-only).

## 1. Architecture

PAGE → primary OCR (existing chain) → writeback → routing decision
(`should_run_secondary`: mode + verdict/confidence/route, never without
primary text, never same-engine twice, never BLANK) → independent second
pass (fresh render; Tesseract default) → `PATCH pages {ocr2}` →
`signals.secondary {done|failed}` → NEEDS_REVIEW stays → human compares →
verifiedText (only promotion path) → reindex/search as before.

## 2. Primary / secondary engines

Primary: existing chain (EasyOCR default). Secondary: `OCR_SECONDARY_ENGINE`
(default `tesseract`), resolved via the engine registry; unknown/unavailable
names record a recoverable error, never crash the run. Model/version/conf
stored per capture; confidences displayed as engine-reported numbers, never
"accuracy".

## 3. Routing (`OCR_SECONDARY_MODE`, default `review`)

- `review`: primary verdict REVIEW / caller-flagged / HANDWRITTEN / conf <
  `OCR_SECONDARY_MIN_CONF` (0.5). Conservative per Phase 12 §16.
- `always`: every page with primary text (explicit opt-in).
- `off`: single capture (rollback switch, zero code change).
- The Phase 12 plan's "default on" is implemented as on-for-review —
  justified by Parts 4/16/28 and this phase's title; full-always would run
  Tesseract twice per page by default, which the brief forbids.

## 4. Database fields (`BookPage`, all nullable/additive)

`ocrTextSecondary`, `engineSecondary`, `ocrConfidenceSecondary`;
`signals.secondary {status: done|failed|queued, engine?, error?, at}` and
`signals.review {at, from: primary|secondary|manual}` (verify audit).
Legacy NULL rows render/index exactly as before.

## 5. Review workflow

Admin review dialog: raw primary + normalized + verified editor (unchanged)
PLUS secondary panel (engine/conf) with rough word-overlap note (labeled
similarity-only), "use secondary as verified base" (still requires Save),
and re-capture when absent. Verify records `signals.review.from`, proving
which capture the human approved. Public viewer untouched (verified/primary
only) — secondary is a review aid, never authoritative text.

## 6. Verification, search, RAG (unchanged policies)

verifiedText ?? ocrText everywhere (reindex, retrieval, viewer). Secondary
never indexed, never a separate document (1 page = 1 doc, asserted live),
never fed to the AI layer. NEEDS_REVIEW preserved through secondary writes.

## 7. Retry & resumability

Secondary state derives from stored columns (`secondary_complete`), so
restarts skip finished captures; failures (`signals.secondary.failed`)
retry on the next pass plus explicit `retry-secondary` action (clears
secondary only — primary/attempts/status untouched). Secondary-only revisits
(`OCR_DONE`/`NEEDS_REVIEW` lacking secondary) avoid primary re-OCR;
`take=500` listing bound documented. Job counters track primary only.

## 8. Retry behavior & fail-safe matrix (live, real pages)

| Case | Result |
|---|---|
| primary ok + secondary ok | both stored, NEEDS_REVIEW kept |
| primary ok + secondary engine bogus | primary kept; `signals.secondary.failed` recorded; page stays reviewable; retry recovers |
| secondary write 401 | local state untouched; retried next pass |
| kill mid-run | zero partial writes; consistent counters |
| blank/handwritten-empty | secondary skipped |
| mode off | zero secondary columns (rollback path proven) |

## 9. Performance (measured, real pages, fresh processes)

Primary-only: 104.4 s/page. Dual: 108.1 s/page (+3.7 s Tesseract).
Model loads dominate; sequential memory profile unchanged.

## 10. Real-book tests (Fatawa vol4, scratch DB, verified by direct reads)

p100: easyocr 0.25/1703ch + tesseract 0.48/1472ch, distinct, NEEDS_REVIEW;
verify-with-secondary-base → `signals.review.from=secondary`, raw-errors
intact both sides; reindex → 1 doc whose body == verifiedText; search hits
it with provenance; p50 mode-off → no secondary columns; p51 dual complete.
Misadventure log: parallel `phase13b.db` confusion (stale duplicate book/job)
resolved by DB-identity proofs — E2E now asserts IDs against direct reads.

## 11. Known limitations

- No consensus correction (agreement research stays in eval/).
- Tesseract confidence uncalibrated (displayed, never compared).
- Secondary text excluded from search/RAG by design (review surface only).
- 500-row listing cap bounds single-pass resume discovery.
- No Nastaliq/specialist coverage change in this phase.
