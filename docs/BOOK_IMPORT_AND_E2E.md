# Book Import & End-to-End — Phase 8 Deliverable

> Real PDF ingestion is operational: multipart upload → checksum dedupe →
> `storage/` originals → jobs → Python worker → writeback → review →
> indexing → search/viewer. Small samples only; no production books ingested.

## 1. Upload flow (`POST /api/admin/import`, multipart only)

Auth (shared key) → `File.size` pre-check → buffer → size recheck (client size
untrusted, `NUR_MAX_UPLOAD_MB`, default 100) → magic bytes `%PDF-` (MIME
ignored: `.txt` → 415 live-verified) → sha256 → duplicate → 409 with existing
book (never overwrite/delete) → Book create (title required, auto-slug,
validated volumes/authorId) or verified existing id → `mkdir -p` +
`writeFile(..., {flag:"wx"})` (no silent overwrite) → orphan cleanup (partial
unlink; just-created book removed; pre-existing books always kept) → 201
`{book, sourceRef, checksum}`. IMPORT only — processing starts separately
(Phase 5 job API or worker `--create-job`).

## 2. Storage & sourceRef

`storage/books/{bookId}/original.pdf`, `sourceRef` = that relative path
(stable, never absolute, never client input). `/storage/` gitignored;
server-side only; non-executable content; deployment must volume-mount it
(standalone `output` keeps CWD storage locally). Caddy imposes no filesystem
constraints. Helpers in `src/lib/book-import.ts` (magic, limits, sha256,
traversal-safe resolve, slug) — unit-tested.

## 3. Worker execution (real, no mocks)

`runner.py --source-ref` resolves via `NUR_STORAGE` (+ traversal guards,
`storage.py`, tested) — **must point at the server's storage dir** (worker
CWD differs; misconfiguration fails closed with a clean message). Digital
pages bypass OCR (`pymupdf-digital`); scans go render→preprocess→EasyOCR→
verify (`--limit`, resumable set, per-page atomic PATCH, counters refresh).
Writeback failures (401) leave server state untouched; auth/config failures
exit cleanly (fixed during testing — was a traceback).

## 4. E2E evidence (2026-09-27, scratch DB + dev server :3100)

- Fatawa-style digital 3pp: upload 201 (checksum recorded, file verified
  byte-identical) → job → worker 3/3 digital, 0 OCR → reindex 3 docs →
  search finds all with vol/page provenance.
- Tibyan-style scanned 2pp: worker 1 OCR_DONE (0.75) + 1 NEEDS_REVIEW
  (honest low-confidence flag) → review queue → verified-text saved, raw kept
  (91 vs 53 chars) → reindex 2 docs → verified text searchable.
- Duplicate re-upload → 409; oversize (1MB cap) → 413; bad PDF → 415;
  missing source → clean exit 1; bad key → clean 401 exit, page untouched;
  bad reindex id → 404; INDEXED pages refuse fail (409 by design).
- Resume: rerun selects 0 (no reprocessing); mid-run SIGKILL → consistent
  state, zero partial writes; restart completes with exactly-once attempts;
  FAILED→rerun recovers; NEEDS_REVIEW correctly excluded from auto-resume.
- Review→verify→reindex→search loop closed on real data.
- AI: no provider configured (`.z-ai-config` absent, verified) → stream
  retrieving→generating→error path stands; citation integrity per Phase 6
  proof (same code). TEST-A question named only if material supports it —
  samples are synthetic markers, so no model claims are made here.

## 5. Data integrity (inspected live)

3 books (sourceRef+checksum all set); 7 pages (3+2 INDEXED, 1 NEEDS_REVIEW,
1 FAILED-probe); 4 jobs; 5 BOOK_PAGE docs; reviewed page keeps raw+
normalized+verified; 6/7 pages verifiedText-NULL (only reviewed set);
resume-book correctly unindexed (not ready until indexing — enforced by
workflow, not UI claims).

## 6. Regression & platform notes

- bun **80/80**, pytest **56/56**, eslint **exit 0**; `next build` compiles
  (Windows `cp -r` packaging step still fails — pre-existing, untouched).
- P2022 caught live: old scratch DBs need `db push` after additive columns.
- Windows: all new paths via `path`/`os.path`/`fs/promises`; no subprocess,
  no new shell commands; XHR used for upload progress (fetch lacks it).
- Memory: multipart buffers to the cap (documented bound); worker stays
  page-incremental; viewer paginates (≤50); PDFs never in browser memory.
- No browser tooling here: admin upload UI exercised via API (same endpoints/
  payloads); rendering asserted by build + code review, not screenshots.
- Scratch: `storage/` originals + temp DBs/scripts are E2E artifacts —
  production storage needs backup/volume policy before any real ingest.
