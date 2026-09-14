# Frontend Book Integration — Phase 7 Deliverable

> Book processing wired into the EXISTING SPA (hash router, Zustand,
> shadcn/Radix design system, trilingual RTL). No new app, no second viewer,
> search, chat, state system, or design language.

## 1. Frontend/backend integration map

| Surface | Backend consumed | Notes |
|---|---|---|
| Admin → Book processing | `GET/POST/PATCH /api/admin/ingest`, `GET/PATCH /api/admin/pages`, `POST /api/admin/reindex`, `GET /api/books` | all mutations keyed (`apiAdmin`); backend authoritative |
| Source viewer pages tab | NEW `GET /api/books/pages?slug=&volume=&take(≤50)&skip=` (public, paginated) | only small backend addition this phase |
| Search filters | `GET /api/search?q=&type=&bookId=&volume=` | every control hits the backend |
| QA citations | `GET /api/questions?id=` (now includes citations+book slugs), generate/stream `done.answer` (refetched with citations) | smallest compatible change for links |
| Admin book metadata | generic `admin/resource` passthrough (no new endpoint) | only persistable columns exposed |

## 2. API consumption (`src/lib/book-api.ts`)

Centralized typed client: `fetchProcessingJobs/Status`, `createProcessingJob`,
`patchProcessingJob` (advance/cancel/retry), `fetchPages`,
`patchPage` (verify/requeue/fail), `writePageOcr`, `fetchBookPages`,
`triggerReindex`. Keyed GETs use `apiAdminGet` (same shared-key convention).
Pure helpers (tested): `buildBookPageParam`, `parseSourcesParam`,
`formatJild`, `isTerminalJob`, `jobProgress`, status-meta maps. No React
Query in this codebase (plain fetch + state, as existing); no raw fetches
outside the client.

## 3. Processing job UI (`book-processing.tsx` in `#/admin`)

Book selector → create-job form (volume, totalPages→stubs, sourceRef;
originals stay in `storage/`, never uploaded — no upload endpoint exists) →
job cards (status badge w/ text, stage, progressbar + %, total/done/failed/
review, started/updated/completed, error, cancel/retry/reindex/check-status)
→ review queue (NEEDS_REVIEW + failed lists). Polling 5s while active + refetch
on tab-visible (no job SSE endpoint exists; documented); backend state rules.
All states: loading skeletons, empty, error+retry, toasts.

## 4. Review workflow

Review dialog per page: raw OCR (read-only, `dir=auto`), normalized index
text, editable verified textarea, confidence/engine/language/attempts,
reason, status badges. Save → `verify` (+verifiedText); requeue/fail paths
included. Raw OCR never overwritten by review (separate column, asserted).

## 5. Source viewer (`#/sources`, reused)

`book/{slug}/{page?}` deep-links (hash parser extended, refresh/share-safe).
Pages tab replaced the placeholder with volume select (jild labels),
paginated list (20/page), and reader: metadata ledger, stored image or
no-image notice, verified block (green-framed) vs raw OCR (UNVERIFIED-labeled,
never authoritative-looking), ShareBar citing the page path, overlay-ready
`<img>` for future box highlighting. No new reader.

## 6. Search results + filters

BOOK_PAGE hits render book/author/jild/chapter/page/verified from the real
`provenance` payload (nothing reconstructed client-side); click deep-links
`book/{slug}/{page}`. Filters: type chips (+Passages), book dropdown, jild
number — all in the backend request. Provenance UI verified live.

## 7. Citation flow

`AnswerCitations` in `AnswerCard`: book rows show title/author/Jild/page/
chapter/quote + `VerificationBadge` (existing VERIFIED/…/UNVERIFIED vocabulary)
+ "Open source" → `#/sources/book/{slug}/{page}`. `EvidenceList` renders
`jild`/`page`/`verification` fields. Unverified stays visually distinct
(amber badge + lead-only wording); no invented metadata (conditional render).

## 8. AI flow (unchanged) + no-AI behavior

Ask submit-only (verified, untouched); QA streaming intact. Stream failures
now render an inline alert (error + Retry + Search fallback) instead of
toast-only — retrieval/search/library keep working when the model is down
(live-proven: SSE retrieving→generating→error with graceful UI path ready).

## 9. RTL / i18n / dark / mobile / a11y

~55 `bp*` keys × EN/UR/AR (no hardcoded visible strings; `??` fallbacks are
dead code once keys exist). `dir=auto` on mixed text, `formatJild` locale
labels (no manual reversal), `rtl:rotate-180` chevrons, `font-arabic` blocks,
existing dark tokens only, `role=progressbar`/`alert`/`aria-label`s, icon+text
badges (never color-alone), keyboard-native buttons/dialogs, responsive
grids stacking at 390px (verified by class review; no browser tool here).

## 10. Permissions

Admin mutations keyed; reads follow existing open-GET conventions. No
frontend-only security (backend 401s without key). Normal users gain no admin
surface: processing/review UI lives only in `#/admin`.

## 11. Verification (run 2026-09-27)

| Check | Result |
|---|---|
| bun tests | **73 pass / 0 fail** (7 files: +6 frontend contracts) |
| eslint | **exit 0, clean** (2 setState-in-effect violations found + fixed) |
| `next build` | compiles (routes listed); Unix `cp -r` packaging step fails on Windows — pre-existing script issue, unrelated |
| live dev server (scratch DB) | `/` 200; pages endpoint (vol/page/chapter/texts); search+provenance; volume/type filters; Q&A citations w/ slugs; job create→QUEUED→status→cancel; review queue; reindex (1 doc) |
| search→source chain | `live6 milad` → BOOK_PAGE → `book/live6-fatawa/112` → page confirmed |
| python suite | untouched this phase |
| Browser rendering (Part 31) | NOT verifiable here — no browser tooling; HTTP + build + code-review only. RTL/dark/390px asserted by construction (existing tokens/patterns), not screenshots |

## 12. Known limits

- No PDF upload endpoint exists → admin takes `sourceRef`, not files.
- Book editor exposes only persistable columns (no category/year/type —
  backend has none; not faked).
- `section` in citations/provenance is null until page anchors land.
- Polling (5s), not SSE, for jobs (no job SSE endpoint; smallest mechanism).
