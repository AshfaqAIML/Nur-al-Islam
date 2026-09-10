# Book Processing Foundation — Phase 2 Deliverable

> Orchestration foundation only. **No OCR engine implemented** ( `POST /api/ocr` unchanged).
> Audit reference: `docs/BOOK_PIPELINE_INTEGRATION_AUDIT.md` (§11–§13 planned exactly this shape).

## 1. What was added (canonical root `Nul al usal front/` only)

| File | Purpose |
|---|---|
| `prisma/schema.prisma` | `BookProcessingJob` model; `Book.jobs` relation + `Book.sourceRef`; `BookPage` += `status/language/engine/checksum/error/attempts` |
| `src/lib/book-processing.ts` | Pure job/page state machine (no DB imports — unit-tested) |
| `src/lib/book-jobs.server.ts` | Server-only counter rollup + `Book.ocrStatus` mirroring |
| `src/app/api/admin/ingest/route.ts` | Job endpoints: create · status · advance · cancel · retry |
| `src/app/api/admin/pages/route.ts` | Page endpoints: list/status · review queue · verify/requeue/fail |
| `tests/book-processing.test.ts` | 17 `bun test` tests, 96 assertions |
| `.gitignore` | `/storage/` — original PDFs/scans, never committed |

## 2. Schema (SQLite conventions preserved: String statuses, JSON-as-String)

**`BookProcessingJob`** — `id, bookId → Book (Cascade), status @default("QUEUED"), stage @default("QUEUED"), progress Float @default(0), totalPages/processedPages/failedPages/reviewPages Int @default(0), startedAt?/completedAt?, error?, metadata? (JSON {sourceRef, requestedBy, notes}), createdAt, updatedAt`, `@@index([bookId])`, `@@index([status])`.
Statuses: `QUEUED ANALYZING EXTRACTING RENDERING OCR STRUCTURING VERIFYING CHUNKING INDEXING COMPLETED COMPLETED_WITH_WARNINGS REQUIRES_REVIEW FAILED CANCELLED`.

**`BookPage` additions** — `status @default("PENDING")` (`PENDING|QUEUED|OCR_DONE|INDEXED|NEEDS_REVIEW|FAILED`), `language?, engine?, checksum?, error?, attempts @default(0)`. Natural key `@@unique([bookId, volume, pageNumber])` untouched. (Deviated from the audit's suggested `"DONE"` default: `PENDING` keeps resume logic uniform — every job-created page starts resumable.)

**`Book.sourceRef?`** — pointer to the preserved original (e.g. `storage/originals/<book>.pdf`).

**Deferred (documented, not done):** `SearchDocument @@unique([entityType, entityId])` — needed before bulk indexing (Phase 3+), deferred to avoid disturbing seed `createMany` flows.

## 3. State machine (`src/lib/book-processing.ts`)

- `JOB_TRANSITIONS`: strict forward chain `QUEUED→…→INDEXING→COMPLETED`, `FAILED`/`CANCELLED` edges from every active state, `VERIFYING↔REQUIRES_REVIEW` review loop, `→COMPLETED_WITH_WARNINGS` from `INDEXING`/`REQUIRES_REVIEW`. Terminals have no exits.
- `cancelJob`: any non-terminal → `CANCELLED`; terminals/unknown → `null`.
- `retryJob`: `FAILED|REQUIRES_REVIEW|COMPLETED_WITH_WARNINGS` → `QUEUED`; everything else → `null`.
- `summarizePages` (page rows = source of truth: processed=`OCR_DONE|INDEXED`, failed, review, resumable=`PENDING|QUEUED|FAILED`), `computeProgress` (0-guarded, clamped), `deriveFinishedStatus` (failed > review > completed).

## 4. API (all methods require `x-admin-key`; scope `ingest`, 30/min)

**`/api/admin/ingest`**
- `POST {bookId, totalPages? (0..10000), volume? (=1), metadata?}` → `201 {job}`. Validates book exists (`404`); rejects duplicate active job per book (`409` + `jobId`); creates idempotent `PENDING` page stubs (only missing numbers); sets `Book.ocrStatus=IN_PROGRESS`.
- `GET ?jobId=` → `200 {job, summary}` (live recompute from pages + `progress`); `GET ?bookId=` → `200 {jobs}` (20 latest); else `400`.
- `PATCH {jobId, action}`:
  - `advance {to}` — `canTransitionJob`-validated; sets `startedAt` leaving `QUEUED`, `completedAt` on terminals; mirrors `Book.ocrStatus`. Illegal → `409`.
  - `cancel` — → `CANCELLED` (+ `completedAt`, error note); reverts book to `NOT_STARTED` if no other active job. Terminal → `409`.
  - `retry` — → `QUEUED` (clears `completedAt/error/failedPages`) **and resets that book's `FAILED` pages → `PENDING`** (resume). Ineligible → `409`.

**`/api/admin/pages`**
- `GET ?jobId= | ?bookId=` (+ `reviewOnly=1`, `take` ≤ 500 default 100, `skip`) → `200 {pages, total, summary}` ordered `(volume, pageNumber)`.
- `PATCH {pageId, action}`: `verify` (`NEEDS_REVIEW`→`OCR_DONE` + `verified=true`), `requeue` (`NEEDS_REVIEW|FAILED`→`PENDING`), `fail` (any non-`INDEXED`→`FAILED` + error ≤500 chars). Illegal → `409`. Refreshes the book's latest active job counters.

Error convention throughout: `{error}` (+ `Retry-After` on `429`), matching existing admin routes.

## 5. File handling

Inspection result: **no storage layer existed** (`download/` = QA screenshots, `db/` = SQLite file, `public/` = PWA assets, no upload handling anywhere). Per "no unrelated storage architecture":
- Originals convention: `storage/<anything>` (gitignored), referenced by `Book.sourceRef` / job `metadata.sourceRef`. **Originals are never mutated** — the pipeline works only on derived `BookPage` rows.
- No multipart upload implemented in this phase (job creation references an already-placed original). Upload transport belongs to Phase 3 alongside the OCR worker.

## 6. Verification (run 2026-09-27)

| Check | Result |
|---|---|
| `bun test tests/book-processing.test.ts` | **17 pass / 0 fail, 96 assertions** — transitions, cancel, retry, progress, summary/resume, finished-status |
| `prisma validate` | Schema valid |
| `prisma generate` | Client v6.19.3 generated |
| `prisma db push` → scratch DB | In sync; then live round-trip via generated client: book+job+3 pages created, mixed page states stored, `NEEDS_REVIEW` query (1), status-index lookup hit, `sourceRef` stored, `FAILED→PENDING` resume (1), `Book` delete cascaded pages (0) + jobs (0). Scratch DB + probe script removed afterwards |
| ESLint | Still unrunnable (`node_modules/` has only the generated Prisma client; full `bun install` not run — out of scope) |
| Route-level tests (401/409/201 over HTTP) | **Deferred**: needs `next` + DB + running server; checklist below |

## 7. Integration checklist (when deps + server are available)

1. `bun install`, point `DATABASE_URL` at a scratch file, `prisma db push`, seed if needed.
2. `401` without key on all six method/shape combos; `400` on bad bodies; `404` unknown book/job/page.
3. `POST` create → `201` + stubs; duplicate create → `409`; `GET` summary math matches pages.
4. `PATCH advance` through `QUEUED→ANALYZING→…→INDEXING→COMPLETED`; illegal jump → `409`.
5. Page `fail` → counters update; `retry` → failed back to `PENDING`; `cancel` → `CANCELLED`; cancel terminal → `409`.
6. `Book.ocrStatus` transitions: `IN_PROGRESS` → `DONE` / `NEEDS_REVIEW` / `NOT_STARTED` as jobs complete/fail/cancel.

## 8. Stopping point / next phase hooks

- Workers (Phase 3+) call `PATCH …/ingest {advance}` and `PATCH …/pages` per page, then `POST /api/ocr` per page image — the `advance` endpoint exists precisely as that worker hook.
- Indexing phase adds the `SearchDocument` writer + `@@unique([entityType,entityId])` + `BOOK_PAGE` branch in `retrieval.ts` (audit IP-6/IP-7/IP-8).
- Admin UI (`BookIngest` card, `pages` tab viewer) intentionally not built — backend foundation first, per phase scope.
