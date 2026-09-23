# Book Processing State Machine — Phase 14

> Server-enforced transitions (`canTransitionJob`/`cancelJob`/`retryJob` in
> `src/lib/book-processing.ts`, 409 on violation). Workers never transition
> jobs except via `PATCH /api/admin/ingest` (advance/cancel/retry).

## Job statuses

`QUEUED → ANALYZING → EXTRACTING → RENDERING → OCR → STRUCTURING → VERIFYING → CHUNKING → INDEXING → COMPLETED`
Any active state → `FAILED` / `CANCELLED`. `VERIFYING` → `REQUIRES_REVIEW`.
`INDEXING` → `COMPLETED_WITH_WARNINGS`. `REQUIRES_REVIEW` → `VERIFYING`
(re-review), `COMPLETED_WITH_WARNINGS`, `FAILED`, `CANCELLED`.
Terminals (`COMPLETED`, `COMPLETED_WITH_WARNINGS`, `FAILED`, `CANCELLED`)
have no outgoing edges except explicit `retry`:
`FAILED|REQUIRES_REVIEW|COMPLETED_WITH_WARNINGS → QUEUED` (failed pages
requeued inside the same transaction). `COMPLETED`/`CANCELLED` never retry —
create a new job instead.

## Page states (`BookPage.status`)

`PENDING → QUEUED → OCR_DONE → INDEXED`, with `NEEDS_REVIEW` and `FAILED`
as side states. Allowed writes: `ocr` (any → `OCR_DONE`/`NEEDS_REVIEW`),
`verify` (`NEEDS_REVIEW` → `OCR_DONE` + `verified`), `requeue`
(`NEEDS_REVIEW|FAILED|INDEXED` → `PENDING`, texts preserved; indexed pages
leave the index until reprocessed — honest re-examination), `fail` (any
non-`INDEXED` → `FAILED`), `ocr2` (secondary columns only, status untouched),
`retry-secondary` (clears secondary only). `fail` stays refused on `INDEXED`
(use requeue for re-examination).

## Secondary capture states (derived, not a column)

`secondary_complete(row)` = `ocrTextSecondary` present OR
`signals.secondary.status == "done"`. Failed (`"failed"`) retries on next
pass; `retry-secondary` resets to `queued`. Attempts count primary passes
only. Job counters (`total/processed/failed/review`) track primary states;
secondary moves `secondary_done/failed/skipped` run stats only.

## Cancellation semantics

`cancel` allowed from any non-terminal state (transactional with the
`Book.ocrStatus` mirror). Workers poll job status per page and stop promptly
on `CANCELLED` (no partial writes: writebacks are single-row atomic).
A cancelled job never resumes; retry is rejected (409).

## Indexing idempotency

Reindex = `deleteMany(BOOK_PAGE docs of book)` + `createMany` + flip
`OCR_DONE → INDEXED`. Repeating yields identical counts. `NEEDS_REVIEW`
pages stay flagged but searchable. One page = one document always
(`@@unique([entityType, entityId])` enforced; duplicates rejected).

## Verification invariants

RAW (`ocrText`) never overwritten by review/correction flows; corrections
land in `verifiedText`; `signals.review = {at, from: primary|secondary|
manual}` audits each approval. Display/index/RAG prefer
`verifiedText ?? ocrText`; secondary text never indexes and never feeds RAG.
