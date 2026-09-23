# Phase 14 — Production Hardening

> Scope: harden the CURRENT system. No engine changes, no Postgres/Redis,
> no rebrand, no unrelated rewrites. Baseline: Phase 13 + 80 bun / 34 pytest.

## 1. What changed (and what deliberately did not)

- `src/lib/admin-auth.ts` (NEW): one shared admin gate; `ADMIN_KEY` env
  overrides, historic key stays as fallback. All 5 keyed routes import it.
  Open GETs unchanged (dashboard compatibility).
- `ingest` create/cancel/retry wrapped in Prisma transactions (job + stubs +
  counters + `Book.ocrStatus` mirror atomically).
- `resource` book DELETE now also removes that book's `SearchDocument`s
  (chunked) — previously orphaned into stale search hits.
- Worker: per-page cancel-check (stops promptly, in-flight atomic unit
  finishes), corrupt-PDF clean exit, source-checksum gate (refuses moved
  files), secondary-only revisits, `_finish` skips the terminal advance when
  cancelled.
- `pages` API: `pageId` detail (full text states + signals), requeue now
  accepts INDEXED (honest re-examination; leaves index until reprocessed).
- Review UI: verification reasons + verified-from audit display; secondary
  compare + re-capture (unchanged from Phase 13).
- Config: `OCR_SECONDARY_MODE` validated (`review|always|off`); env table in
  `docs/PHASE_14_PRODUCTION_HARDENING.md` §6 of that doc... (see §6 below).
- NOT changed: engines, RAG, search ranking, AI, branding, unrelated views.

## 2. Lifecycle / recovery model

Atomic single-row writes + transactional multi-writes + resumable sets
(`PENDING|QUEUED|FAILED` primary; missing/failed secondary). Kill-tested:
no partial writes, consistent counters, restart completes exactly-once.
Cancelled jobs stop workers promptly; terminals never retry/resume.

## 3. Idempotency model

Checksum dedupe (import), active-job guard (409), stub upsert by natural key,
reindex delete+rebuild (verified 9/9 twice), verify/requeue/fail/cancel
guard by state (409 matrix verified live), retry-secondary clears secondary
only. Duplicate BookPages/SearchDocuments/citations/files structurally
impossible (uniques + keyed writes + `wx` + single doc per page).

## 4. Retry semantics

Page fail → requeue → PENDING (attempts preserved as history). Job retry
requeues FAILED pages transactionally. Secondary retry is independent
(primary/attempts/status untouched). Cancel is terminal; new job required.

## 5. Storage model

`storage/books/{id}/original.pdf`, gitignored, server-side, non-executable
content, checksum-pinned (`sourceChecksum`), verified on worker start,
EEXIST never overwrites, orphans cleaned on failed creates. Deployment must
volume-mount `storage/` (standalone keeps CWD storage locally).

## 6. Configuration (all env, safe defaults)

`DATABASE_URL` (required) · `ADMIN_KEY` (default historic key) ·
`NUR_STORAGE` (default `./storage`) · `NUR_MAX_UPLOAD_MB` (default 100, cap
2000) · `OCR_PRIMARY_ENGINE`/`OCR_FALLBACK_ENGINES`/`OCR_TESSERACT_*` ·
`OCR_SECONDARY_MODE` (`review`) · `OCR_SECONDARY_ENGINE` (`tesseract`) ·
`OCR_SECONDARY_MIN_CONF` (0.5) · `NUR_API_BASE`/`NUR_API_TIMEOUT_S` ·
`NUR_ADMIN_KEY` (worker) · `NUR_EVAL_DIR` (lab only). No behavior depends on
undocumented machine settings.

## 7. Review workflow

Queue (NEEDS_REVIEW) → dialog (raw/normalized/verified/secondary + reasons +
confidence/engine) → edit → Save (verifiedText only; `signals.review`
audits source+timestamp) → reindex → search uses verified text. Secondary
never auto-promotes ("use as base" still requires Save).

## 8. Indexing rules

One page = one `BOOK_PAGE` doc; display = `verifiedText ?? ocrText`;
`bodySearch` normalized; meta provenance; reindex idempotent; NEEDS_REVIEW
stays searchable-but-flagged; legacy NULL rows unaffected.

## 9. RAG evidence boundary

Original → OCR → review → verifiedText → SearchDocument → retrieval →
context → citation. Secondary text never enters retrieval/index/AI
(grep-verified). Citations resolve Book→Jild→Page→viewer via FK-backed rows.

## 10. Operational procedures

- Pilot: metadata-only book → job(totalPages) → worker `--pages` ranges →
  review → verify → reindex → search. 10-page pilot: 10/10 review-routed,
  10/10 dual-captured, 0 failed.
- Failure recovery: kill → restart (proven); cancel → stopped promptly
  (proven live, `{"cancelled": true}`); corrupt PDF → clean exit 1; bad key →
  clean 401 exit, server state untouched; missing source → clean exit.
- Restarting the app/server is stateless-safe (all state in SQLite).

## 11. Failure recovery procedure (operator)

1. Inspect job (`GET ingest?jobId`) + pages (failed/review lists).
2. Fix cause (engine/key/source), then: failed pages → worker rerun or
   requeue; stuck secondary → `retry-secondary`; bad job → cancel + new job.
3. Re-verify a sample page detail, reindex, spot-check search.
4. Never hand-edit the DB; never delete storage originals.

## 12. Pilot results

10 real Fatawa pages: selected 10, done 0 / failed 0 / review 10,
secondary 10/10, 0 failed, resumable math exact, no duplicates, provenance
intact, originals untouched. Dual cost +3.7 s/page over ~104 s primary.

## 13. Known limitations / remaining risks

- 500-row listing cap bounds single-pass discovery (documented; chunked
  client loops as follow-up).
- Review labor dominates (real scans triage ~100%).
- Tesseract confidence uncalibrated; Nastaliq/specialist unevaluated.
- Single-node SQLite (documented swap path, not this phase).
- No browser-tooling verification of new admin UI strings (build + API
  verified; RTL/dark by construction).

## 14. State machine

Full transition tables: `docs/BOOK_PROCESSING_STATE_MACHINE.md`.
