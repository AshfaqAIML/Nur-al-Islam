# Phase 14 — Production Readiness Report

## Executive summary

The book pipeline is hardened and pilot-proven on real books. All validation
gates pass. No engine, RAG, AI, or branding changes. Recommended: READY for a
controlled production-scale pilot (not unsupervised bulk ingest).

## What was changed

Transactional job create/cancel/retry; centralized admin auth (env-overridable,
backward compatible); SearchDocument cleanup on book delete; worker
cancel-checks, corrupt-PDF exits, source-checksum gate, secondary-only
revisits; review reasons + verify-audit display; requeue-from-INDEXED;
`pageId` detail endpoint. Details: `docs/PHASE_14_PRODUCTION_HARDENING.md`,
state tables: `docs/BOOK_PROCESSING_STATE_MACHINE.md`.

## What was intentionally not changed

OCR engines/routing defaults, RAG/search/AI, Postgres/queues/cloud,
branding, unrelated features, open-GET conventions.

## Test results

- Bun 80/80 · pytest (dual/storage/metadata/normalize/contract + eval 15) green
- ESLint 0 · Next build compiles (pre-existing Unix `cp` packaging caveat)
- Migration: clean push + existing-DB push, data intact (1/100/1/12 + p100 verified)

## Real-book pilot results (Fatawa vol4, 10 pages)

Selected 10 → done 0 / failed 0 / review 10, secondary 10/10, resumable math
exact, provenance intact, originals untouched, dual +3.7 s/page over ~104 s.

## Recovery results

Kill mid-run (twice, incl. SIGKILL-equivalent): zero partial writes,
consistent counters, exact-once resume. Cancel mid-run: worker stops
promptly (`{"cancelled": true}`), in-flight atomic unit completes, terminal
advance correctly refused. Corrupt PDF/missing source/bad key: clean exits,
server state untouched. Secondary failure: recorded, primary kept, retry works.

## Idempotency results

Double create/verify/cancel → 409s; reindex twice → identical counts;
checksum dedupe → 409 without overwrite; reruns select 0 done pages.

## Storage integrity results

Originals immutable (checksum-verified pre-run); EEXIST never overwrites;
orphan cleanup on failed creates; traversal rejected (tested); book delete
cascades pages+jobs+search docs.

## Search/index results

Reindex idempotent (9/9 twice); 1 page = 1 doc; verifiedText preferred;
secondary never indexed; NEEDS_REVIEW searchable-but-flagged; legacy rows
unaffected; provenance (vol/page/chapter/book/author) survives end-to-end
(search → viewer deep-link verified live in Phase 7/8).

## Provenance results

Book→Jild→Page→viewer chain intact; citation rows resolve with slugs;
`signals.review.from` proves human-approval source; raw/secondary/verified
texts independently preserved (length-verified).

## Known OCR limitations (unchanged)

EasyOCR coverage 0.18–0.67 on real scans; Tesseract faster but overconfident;
Nastaliq/specialist unevaluated; review rate ~100% on real scans.

## Known remaining risks

500-row listing cap; review-labor bottleneck; single-node SQLite; no browser-
tooling UI screenshots (build+API verified); scratch E2E books live only in
temp DBs (production DB untouched).

## Recommended next phase

Controlled production-scale pilot (single real volume, 50–100 pages) with the
Phase 14 operational procedures, then Linux/GPU eval host for Paddle/Qaari
per the Phase 12 decision. No architecture changes proposed.
