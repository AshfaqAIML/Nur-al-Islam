# Production OCR Implementation Plan — Phase 12 (APPROVED → IMPLEMENTED Phase 13)

> Trigger ONLY on explicit approval of `PRODUCTION_OCR_DECISION_V2.md` §12.
> Phase 13 implemented this plan with the deviations below (all conservative).
> Rollback is designed first.

## Files / modules

- `prisma/schema.prisma`: `BookPage` += `ocrTextSecondary String?`,
  `engineSecondary String?`, `ocrConfidenceSecondary Float?` (all nullable;
  additive `db push`, no backfill — NULL = single-capture legacy rows).
- `mini-services/ocr-worker/runner.py`: after primary writeback, run
  Tesseract adapter on the same rendered image, `PATCH pages {action: ocr2}`
  (new action, same validation shape as `ocr`).
- `src/app/api/admin/pages/route.ts`: `ocr2` action (keyed; writes only the
  three secondary columns; never touches raw/verified).
- `src/components/platform/book-processing.tsx` + `book-pages.tsx`: review
  dialog and reader show primary vs secondary side-by-side with a textual
  diff note (reuse `ConsensusEngine.compare` numbers, read-only).
  [Phase 13 as-built: side-by-side + word-overlap note in the ADMIN review
  dialog only; public reader unchanged by design (secondary is review-only).]
- `src/app/api/admin/reindex/route.ts`: UNCHANGED policy (verifiedText ??
  ocrText); secondary text never indexes directly.
- `src/lib/i18n.ts`: `bpSecondary*` keys × EN/UR/AR.

## Configuration / routing / rules

- `WorkerConfig`: `OCR_SECONDARY_ENGINE=tesseract` (default on),
  `OCR_SECONDARY_LANGS=urd+ara+eng`; primary chain untouched.
  [Phase 13 as-built: `OCR_SECONDARY_MODE=review|always|off` (default
  `review`) + `OCR_SECONDARY_MIN_CONF=0.5` — "default on" implemented as
  on-for-review per the brief's anti-always-run rule; full-always is opt-in.]
- Confidence rules: Tesseract confidence down-weighted (Phase 11 §10);
  cross-engine comparison forbidden in routing logic.
- Fallback rules: secondary failure → warn + continue (primary record
  suffices); primary failure → existing FAILED path.
- No consensus correction: disagreement surfaces as review priority only.

## Database impact

Additive nullable columns; existing rows read identically; old clients
ignore new fields. Indexing, retrieval, AI, and frontend behave exactly as
today until review promotes verified text.

## Worker impact

+1 OCR pass per page (~+10–20 s on current CPU); resumability unchanged
(secondary write is idempotent per page); memory unchanged (sequential).

## Tests

- Unit: `ocr2` validation, secondary-column persistence, review-UI rendering
  with/without secondary data, i18n keys ×3.
- Lab gate: rerun `eval/bench.py` on all 7 real pages + 10 new GT lines;
  acceptance = union coverage gain AND no regression on primary metrics.
  [Phase 13 outcome: gate reinterpreted — capture (not union-routing) was
  approved for review support; auto-merge stays deferred. Details:
  `docs/DUAL_CAPTURE_OCR.md` §10.]
- Regression: full bun/pytest/eslint/build as today.

## Benchmark requirements

Gate metrics before merge: per-page union bounds strictly above best-single
on ≥5/7 pages; Tesseract calibration mapping documented; review-rate impact
measured. Otherwise STOP — keep single capture.

## Rollback plan

- Current config: EasyOCR-only primary (`ocrText`, `engine`, `ocrConfidence`).
- New config: additive columns + `OCR_SECONDARY_ENGINE` flag (default on).
- Toggle: set `OCR_SECONDARY_ENGINE=` empty → worker skips secondary pass;
  API/UI render primary-only when secondary columns are NULL (already the
  default branch).
- Rollback process: (1) unset the flag, (2) optional `db push` dropping the
  three columns (SQLite: recreate-table migration; data loss limited to
  secondary captures, primary/verified untouched), (3) rerun lab gate to
  confirm single-capture behavior.
- Database safety: no column renames/drops on existing fields; BookPage
  primary text, verified text, citations, and SearchDocument rows are never
  touched by secondary writes.
- Existing BookPage compatibility: legacy rows (NULL secondary) render and
  index exactly as today.
