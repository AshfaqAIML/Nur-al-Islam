# Book Pipeline Integration Audit — Nur al-Usul

> **FIRST TASK deliverable. Read-only audit. No code was written or modified to produce this document** (this file itself is the only artifact).
> Source code is authoritative; the README is treated as architectural reference only.

| Item | Value |
|---|---|
| Audit date (UTC) | 2026-09-27 |
| Auditor | AI agent (read-only sweeps + direct source verification) |
| Canonical app root | `Nul al usal front/` |
| Schema file | `prisma/schema.prisma` (479 lines, 23 models) |
| Runtime | Bun; Next.js 16 App Router (`output: "standalone"`); React 19; TS 5 |
| DB | Prisma 6 + SQLite (`DATABASE_URL=file:./dev.db`) |
| LLM | `z-ai-web-dev-sdk@0.0.18`, server-side only |

## 0. Canonical repository decision

Both folders were compared by SHA-256 over all files (excluding `.git`, `node_modules`, `.next`):

- `Nul al usal front/`: 220 files · `Nur al asul process/`: 219 files.
- **Only differences:** (1) `README.md` — present only in `Nul al usal front/` (committed as `1a63ecd`, pushed to `origin/main` at `github.com/AshfaqAIML/Nur-al-usal.git`); (2) `.zscripts/dev.pid` — ephemeral dev-server PID file, content differs meaninglessly.
- **All 219 shared source files are byte-identical.**

**Selected canonical root: `Nul al usal front/`** — it is the copy that tracks `origin/main`, contains the README, and has `core.fileMode=false` set locally (to suppress the pre-existing `100755→100644` mode-noise across the tree). **Do not make divergent changes to both folders.** Recommended follow-up: archive or delete `Nur al asul process/`, or repoint it at a separate repo — it currently shares the same `origin` URL with a diverged HEAD and will conflict on push.

> Note: this audit document is created **only** in the canonical root (`Nul al usal front/docs/`). It must not be copied into the non-canonical folder by hand; folder sync, if ever needed, must be an explicit operation.

---

## 1. Current architecture

```text
Browser SPA (hash router, src/app/page.tsx + src/lib/store.ts)
  13 views: home knowledge bank misconceptions claims objections
           compare sources quran search ask qa admin
  Zustand store · trilingual EN/UR/AR + RTL · next-themes dark mode
  PWA: manifest + sw.js + offline.html (ServiceWorkerRegister in page.tsx)
        │
        │  REST JSON + SSE (text/event-stream), admin key header
        ▼
Next.js API routes (src/app/api/** — 28 route files)
  rate-limit.ts (per-IP sliding window) → retrieval.ts (KB grounding)
  → ai.ts (llmComplete) / llm-stream.ts (SSE) → ZAI SDK (server-only)
        │
        ▼
Prisma Client singleton (src/lib/db.ts, log:['query']) → SQLite file
  23 models · seeded by prisma/seed.ts + prisma/seed-bank.ts
```

Key design facts (verified):

- **Hash SPA on `/`.** `src/app/page.tsx` `CurrentView()` switches on `view`; `param` deep-links (`#/sources/book/:slug`, `#/claims/:id`, `#/qa/:id`, `#/compare/:id`, `#/search/:json`). `key={view}` remounts on view change only; param changes preserve state. `hydrateFromHash()` restores view/param + `nur-lang` (`src/lib/store.ts`).
- **SQLite now, PostgreSQL later.** `prisma/schema.prisma:1-8` documents the mapping: enums → unconstrained `String`, JSON → serialized `String`. Any pipeline schema addition must follow the same convention (no native enums, no native JSON operators).
- **Single LLM call, dual output.** The streamed draft the user watches *is* the text the parser persists (answers + claims). There is exactly one answering layer — it must be reused, not duplicated.
- **`mini-services/` is empty** (only `.gitkeep`, verified by directory read). There is **no Python worker, no OCR service, no queue** in the repo today.
- **Reverse proxy:** `Caddyfile` listens `:81`, default `reverse_proxy localhost:3000` with `Host/X-Forwarded-For/X-Forwarded-Proto/X-Real-IP` passthrough; `?XTransformPort=*` routes to a dynamic local port (preview mechanism). Rate limiting reads IP from `x-forwarded-for`/`x-real-ip` (`src/lib/rate-limit.ts:51-54`), so the Caddy header passthrough is load-bearing — do not strip it.
- **Build:** `output: "standalone"` (`next.config.ts`), served via `bun .next/standalone/server.js`; `typescript.ignoreBuildErrors: true`, `reactStrictMode: false`.

---

## 2. Existing book/source architecture

There is a **metadata catalog, not a processing pipeline.** Books exist as catalog rows with a page table that is currently write-only-by-design (nothing in `src/` writes it) and read by nothing in `src/`.

| Piece | File | State |
|---|---|---|
| `Book` catalog CRUD (metadata only) | `src/app/api/admin/resource/route.ts` (`book` entity), `src/components/platform/admin-editor.tsx` | Create/edit `titleEn/Ar/Ur, classification, descriptionEn, verified, featured` — no file/upload/volumes/author-link/OCR fields |
| `Book` public read | `src/app/api/books/route.ts` (GET only, no pagination) | List + `?slug=` detail with author + fatwas |
| `BookPage` read/write | nowhere in `src/` | **Zero `db.bookPage` references in `src/`** (verified by repo-wide grep) |
| `Book.ocrStatus` | `src/app/api/admin/stats/route.ts:27` (count only), sources view `pages` tab (display only) | Values written only by seed/admin passthrough; no worker transitions it |
| Source viewer | `src/components/platform/views/sources.tsx` (~book dialog with `overview\|pages\|citation` tabs) | `pages` tab is a dashed **placeholder** (`ManuscriptPanel` + `OCR pipeline status: {ocrStatus}`); `overview` points to `Admin → Upload PDF` (which does not exist yet) |
| Fatwa page backfill hook | sources view fatwa cards (`TBD`/`requestOcr` badge) | Display badge only, no handler behind it |

Net: the schema *anticipates* page-level OCR (`BookPage.ocrText/ocrConfidence/imageUrl/verified`, `Book.ocrStatus`, `Citation.bookPageId/volume/page/ocrConfidence/humanVerified`) but **no runtime code populates or consumes any of it.**

---

## 3. Current database schema relevant to books

`prisma/schema.prisma`. All PKs are `String @id @default(cuid())`. Only env var: `DATABASE_URL`.

### 3.1 `Book` (`schema.prisma:59-90`)

Fields: `id, slug @unique, titleEn, titleAr?, titleUr?, altTitles?, authorId? → Scholar?, era?, school?, subject?, language?, descriptionEn/Ur/Ar?, publisher?, edition?, volumes Int @default(1), chapters? (JSON [string]), classification @default("CLASSICAL_HANAFI"), isHanafi @default(true), ocrStatus @default("NOT_STARTED"), verified @default(false), coverColor @default("emerald"), featured @default(false), createdAt, updatedAt`.
Relations: `fatwas Fatwa[], citations Citation[], pages BookPage[]`.
Indexes: only `@unique(slug)`. **No index on `authorId`, `classification`, `verified`, `featured`.**

### 3.2 `BookPage` (`schema.prisma:92-108`)

Fields: `id, bookId → Book (onDelete: Cascade), volume Int @default(1), pageNumber Int, chapter?, ocrText? (unbounded TEXT), ocrConfidence Float?, imageUrl?, verified @default(false), createdAt, updatedAt`.
Relations: `citations Citation[]`.
**Uniqueness: `@@unique([bookId, volume, pageNumber])`** (`:107`) — the natural key any ingest upsert must use. No FTS index on `ocrText`. **Missing for pipeline use:** no `language`, no `embedding`, no `chunkIndex`, no content `checksum/hash`, no `ocrEngine`, no `imageWidth/Height`, no `processingStatus`/`error` columns.

### 3.3 `Scholar` (`schema.prisma:31-57`)

`id, slug @unique, nameEn, nameAr?, nameUr?, title?, birthYear?, deathYear?, era?, madhhab?, aqeedahTradition?, region?, languages?, biographyEn/Ur/Ar?, majorWorks? (JSON [{title,lang,note}]), classification @default("CLASSICAL_HANAFI"), isHanafi @default(true)`, timestamps. Relations: `books (BookAuthor), fatwas, positions, scholarlyViews`. Only index: `@unique(slug)` — ingest-time author matching must handle slug generation/dedup itself.

### 3.4 `Citation` (`schema.prisma:424-448`)

`id, answerId? → Answer (Cascade, optional so citations can stand alone), sourceType (required String, unenforced convention e.g. QURAN|HADITH|BOOK|BOOK_PAGE|FATWA), quranVerseId? → QuranVerse?, hadithId? → Hadith?, bookId? → Book?, bookPageId? → BookPage?` (all optional, **no check constraint — several can be set at once**), denormalized display strings `volume?/page?/chapter?` (**all `String`, not Int**), `quote?, translation?, verificationStatus @default("UNVERIFIED"), ocrConfidence Float?, humanVerified @default(false), permalink?, timestamps`. No `@@unique`/`@@index` on any FK. Provenance-capable but unenforced; retrieval prompts do not currently consume it (§6).

### 3.5 `SearchDocument` (`schema.prisma:462-479`)

`id, entityType (unenforced String), entityId` (opaque, **no FK, no index**), `title, titleUr?, titleAr?, body (required, full searchable text), bodyUr?, bodyAr?, language @default("EN"), route (frontend link), weight Float @default(1)`, timestamps. **Only index: `@@index([entityType])` (`:478`). No `@@unique([entityType, entityId])`** — duplicates possible; no writer can safely `upsert` today. No FTS index (plain TEXT).

### 3.6 `Review` (`schema.prisma:450-460`)

`id, type @default("EDITORIAL"), action (required), comment?, reviewerId? → User?, targetType (ANSWER|MISCONCEPTION|ARTICLE|CLAIM), targetId` (opaque string, **no FK — polymorphic**), `createdAt` only. No index on `(targetType, targetId)`. Usable as-is for a page-verification audit trail (`targetType` would need a new `"BOOK_PAGE"` convention value; `ARTICLE` exists but is unused by any verified reader).

### 3.7 `Answer` (`schema.prisma:390-422`, abridged)

`id, questionId → Question (Cascade), directAnswer, detailedAnswer?, hanafiPosition?, aqeedahOrFiqh? (AQEEDAH|FIQH|BOTH|NEITHER), quranEvidence?/hadithEvidence?/classicalEvidence?/laterEvidence? (all JSON-string arrays), fatawaRazvia?, otherViews?, commonObjection?, scholarlyResponse?, disputed?, misconceptionNote?, practicalInfo?, sources? (JSON), answerUr?/answerAr? (JSON), status @default("AI_ASSISTED"), revision @default(1), aiGenerated @default(true), helpfulUp/helpfulDown @default(0), userId? → User?, citations Citation[]`, timestamps. Evidence is **opaque JSON strings with no FK to `BookPage`** — page-level grounding would flow through `Citation.bookPageId` + these JSON blobs by convention only.

### 3.8 Text / page / metadata / verification / indexing summary

- **Text storage:** `BookPage.ocrText` (nullable TEXT, unwritten at runtime); `SearchDocument.body` (required TEXT, written only by seeds); evidence JSON-string columns on `Answer/Misconception/Objection`.
- **Page storage:** `BookPage` rows keyed `(bookId, volume, pageNumber)`; `imageUrl?` is a bare string (no storage backend defined — no S3/local-upload convention exists).
- **Source metadata:** `Book` (publisher/edition/volumes/chapters/language) + `Scholar` + `Fatwa.volume/page` (free-form Strings).
- **Verification states:** `Book.verified` bool + `Book.ocrStatus` string (`NOT_STARTED` default); `BookPage.verified` bool + `ocrConfidence Float?`; `Citation.verificationStatus` string (`UNVERIFIED` default) + `humanVerified` bool; `Fatwa.verificationStatus`; `Misconception.verificationStatus`. UI labels come from `VERIFICATION_META` (`src/lib/ai.ts:81-88`: VERIFIED / PARTIALLY_VERIFIED / OCR_NEEDS_REVIEW / UNVERIFIED / DISPUTED / INSUFFICIENT_EVIDENCE) — note `OCR_NEEDS_REVIEW` already anticipated.
- **Search indexing:** `SearchDocument` only (§5/§6). Nothing keeps it in sync with `BookPage` at runtime.

---

## 4. Current OCR architecture

Single endpoint: **`POST /api/ocr`** (`src/app/api/ocr/route.ts`, 99 lines, verified by direct read).

- **Input:** JSON `{ imageBase64: string, mimeType: string }`. Strips `data:` URL prefix (`:35`). No `multipart/form-data`, no file upload, no PDF, no batch array — **one image per request**.
- **Validation:** `400` empty image · `415` unless `image/png|image/jpeg|image/webp` (`:13,28-30`) · `413` over 6,000,000 base64 chars ≈ 4.5 MB binary (`:14,31-33`).
- **Engine:** `z-ai-web-dev-sdk` vision — `zai.chat.completions.createVision({ messages:[{role:"user", content:[{type:"text", text:<verbatim-OCR prompt>},{type:"image_url", image_url:{url:`data:${mimeType};base64,${b64}`}}]}] })` (`:37-60`). Verbatim-extraction prompt: no translation/correction/normalization, preserve paragraphs + footnote line structure, `[illegible]` markers (`:45-58`). Tolerant JSON parse (`raw.match(/\{[\s\S]*\}/)` + `JSON.parse`).
- **Output:** `200 { text (≤8000 chars, :15), language: ar|ur|en|mixed, claimSummary (≤300 chars), chars }`. Errors: `422` empty text, `502` unparseable model output, `500` catch-all, `429` (scope `"ocr"`, 6/min, `rateLimitByIp` `:18-19`).
- **Storage: NONE.** No Prisma import in the file; result is returned to the caller and forgotten. **It does not create `BookPage` records**, does not touch `Book.ocrStatus`, does not write `SearchDocument`.
- **RTL:** response carries `language`; rendering RTL is the *caller's* job — `ocr-attach.tsx` applies `rtl + font-arabic` preview for `ar/ur`. The endpoint itself is script-agnostic (prompt explicitly covers Arabic/Urdu Nastaliq/English, diacritics, footnotes).
- **Confidence data:** none returned (no per-word/per-line scores; no `ocrConfidence` populated anywhere downstream).
- **Reusable:** yes as a single-page extractor — `OcrAttach` (`src/components/platform/ocr-attach.tsx`) already reuses it for Ask-flow quoting (4 MB client check, `png/jpeg/webp`, thumbnail preview, `onQuote(text, claimSummary, language)` into the question textarea). It is also the natural per-page worker for a future batch pipeline (called server-to-server per page image), subject to rate limits + cost.
- **Current limitations:** 1 image/request; ~4 MB cap; 8000-char truncation (lossy on dense pages); no page/volume/book identifiers in or out; no persistence, queue, retry, or job tracking; no `multipart` upload path; in-memory 6/min/IP limit unsuitable for bulk ingest (needs a service-level exemption or separate scope).

---

## 5. Current search architecture

**`GET /api/search`** (`src/app/api/search/route.ts`) over the **`SearchDocument`** table.

- **Query:** `?q= (required), ?type= (mapped to `entityType`), ?lang=, ?surface= (default `"search"`)`. Empty `q` short-circuits (`{results:[], intent:null}`).
- **Lexical only. No semantic/vector search.** Flow: `db.searchDocument.findMany({ where:{entityType?}, take: 500, orderBy:{weight:"desc"} })` (`:34-36`, verified) → in-JS scoring: `title.includes(term) +4`, else `body.includes(term) +2`; prefix fallback (`len>4`) floors at 1.5; `filter score>0`, sort desc, top 30. Snippet = `body.slice(0,220)`. Terms: lowercase split, `len>1`, max 10.
- **Metadata filtering:** `entityType` exact match (DB-side) + soft language filter (JS-side, keeps `lang==lang` only if non-empty). No date/book/author/page filters.
- **Ranking:** title-boost + `weight`-ordered fetch bias (top-500 by weight are the *only* candidates scored). No TF-IDF/BM25 despite a "BM25-lite" comment in `retrieval.ts:6`.
- **Citation generation:** none server-side. Results carry `{entityType, entityId, title(+Ur/Ar), snippet, route, score}`; citable rendering is client-side (`ShareBar` + `buildCitation`, `src/lib/cite.ts:7-24` — display string `Nur al-Usul — …, "Title", section, url, Accessed DATE`, no DB linkage).
- **Logging:** fire-and-forget `db.searchLog.create({query≤300, results, intent, language≤2, surface≤20})` (`:69`) — the **only `SearchLog` writer** in `src/`. `classifyIntent(q)` regexes: source-lookup > evidence > misconception > fiqh > informational.
- **Scale ceiling (verified):** `take: 500` in-memory scan; no pagination/cursor; case-sensitivity depends on SQLite collation (no `mode:"insensitive"`). Indexing thousands of book pages as `SearchDocument` rows will degrade this endpoint linearly unless the retrieval path is reworked (see §16).

---

## 6. Current retrieval architecture (RAG grounding)

**`src/lib/retrieval.ts`** (115 lines, verified via sweep + `take: 400` confirmed at `:32-33`).

- `retrieveEvidence(query, limit=10): Promise<RetrievedDoc[]>`:
  1. `db.searchDocument.findMany({ take: 400, orderBy:{ weight:"desc" } })` — **no SQL-side filtering; all scoring in JS.**
  2. `tokenize`: lowercase, strip non-letters/numbers (Unicode-aware), drop `len≤1`, max 12 tokens. No stemming, no stop-words, **no Arabic orthographic normalization** (alef/hamza/ta-marbuta variants not collapsed — directly relevant to OCR'd Arabic text).
  3. Score: `title.includes(t) +3`, `hay(title+Ur+Ar+body).includes(t) +1`, × `weight`. (Title double-counts since title ⊂ hay → title hit = 4.) `body.slice(0,700)`, sort, `slice(0,limit)`.
  4. Enrichment: per top doc, sequential `findUnique` (+ author/scholar/category includes) rebuilding a formatted body for `MISCONCEPTION|OBJECTION|COMPARISON|HADITH|QURAN|FATWA|BOOK|SCHOLAR|TOPIC` — **N+1 sequential awaits, no `BOOK_PAGE` branch** (a `BOOK_PAGE` doc would pass through with truncated body and no `BookPage` join).
- Helpers: `isSensitiveQuestion` (17-term substring list — talaq/nikah/inheritance/riba/…), `detectLanguage` (Arabic-block + Urdu-specific chars `0679 0688 0691 06BA 06BE 06C1 06C3 06D2 06AF 0686 0698` → UR; `arabic>2` → AR; else EN).
- **Critical, verified facts for pipeline planning:**
  - Retrieval reads **exclusively** from `SearchDocument`. `BookPage.ocrText` is never queried.
  - **No runtime writer of `SearchDocument` exists in `src/`.** Population happens only in `prisma/seed.ts:834` (`createMany`) and `prisma/seed-bank.ts:350` (`createMany`, with `deleteMany` by `entityId` at `:201`). Any book ingest MUST bring its own `SearchDocument` writer or ingested pages will be invisible to both search and RAG.
  - `take: 400` + weight-ordered fetch means corpora >400 docs are silently truncated before scoring.

---

## 7. Current AI answering architecture

One layer only — reuse it. Two transports, same pipeline shape.

- **Shared libs:** `src/lib/ai.ts` — `ANTI_HALLUCINATION_RULES` (`:9-19`: never invent quotes/pages/hadith numbers/titles/authors/Arabic/ijma/fatwas; use only retrieved context; mandatory *"could not be verified"* disclaimer; takfir ban; category distinctions; disputed-grading display; neutral tone), `llmComplete(system, user, {temperature})` (`:25-40`; note system prompt sent as `role:"assistant"`), `extractJson` (fence-tolerant, greedy-brace), `CLASSIFICATIONS` (7 claim verdicts, `:61-69`), `VERIFICATION_META` (incl. `OCR_NEEDS_REVIEW`). `src/lib/llm-stream.ts` — `llmStream(system, user, {temperature, onDelta, signal})` with `SseLineBuffer` + `deltaFromPayload` (OpenAI-style `data: JSON` / `[DONE]`, keep-alive tolerant); `signal` breaks the loop only (does not abort upstream).
- **`POST /api/answers/generate`** (`src/app/api/answers/generate/route.ts`): `{questionId}` → 400/404 checks → sensitive short-circuit (`isSensitiveQuestion` or `question.isSensitive` → 200 + legal disclaimer) → `retrieveEvidence(question.text, 12)` → `llmComplete` JSON-schema prompt (one retry with *"raw JSON only"*) → `extractJson` → `502` if unparseable or `!directAnswer` → `db.answer.create({... status:"AI_ASSISTED", aiGenerated:true})` + `question.update({status:"AI_ANSWERED"})` → `{answer, confidence HIGH|MEDIUM|LOW, unverifiedNote, kbEvidence[0:8]}`. Rate scope `answers-generate` 6/min.
- **`POST /api/answers/stream`** (`src/app/api/answers/stream/route.ts`): same request/validation/sensitive path; SSE `status(retrieving|generating|saving) → delta* → done({answer, kbEvidence, confidence}) / error`. Model writes fixed `##` sections (Direct Answer, Hanafi Position, Evidence with `[Q]/[H]/[C]` bullets, Other Views, Objection & Response, Practical Guidance, Sources); local `parseReadableDraft()` regex-maps sections → `Answer` row (same persistence as generate). **Known drift:** stream `ParsedDraft` omits `laterEvidence/disputed/unverifiedNote`; adds `ref` to quran bullets; unparsed `[Q]/[H]` lines fall back into `classicalEvidence`. Rate scope `answers-stream` 6/min.
- **Claims mirror:** `POST /api/claims` (JSON) + `POST /api/claims/stream` (SSE `retrieving|analyzing|verifying → delta* → done`, `CLASSIFICATIONS` verdict + typed `[Q]/[H]/[C]/[F]/[M]` bullets, confidence heuristic, same `ClaimCheck` persistence). Scope `claims`/`claims-stream` 8/min.
- **How evidence reaches the AI (exact path):** `retrieveEvidence()` formatted strings → interpolated into the system/user prompt as the *only* permitted source context (`ANTI_HALLUCINATION_RULES`) → model output → `extractJson`/section-parse → `Answer`/`ClaimCheck` JSON-string columns. **There is no `bookId`/`pageRange` scoping parameter, no page-number validation, and no `Citation.bookPageId` linkage in this path.** Page-grounded answers require: (a) `SearchDocument` rows for pages, (b) a `BOOK_PAGE` enrichment branch, (c) prompt + parser support for page citations.

---

## 8. Existing source viewer architecture

`src/components/platform/views/sources.tsx` — `SourcesView({param})`, data via `apiGet` (`src/lib/api.ts`).

- Tabs `books|scholars|fatwas` (local state). Lists: `GET /api/books`, `/api/scholars`, `/api/fatwas`. Detail via `GET /api/books?slug=` / `/api/scholars?slug=` → modal `Dialog` (hash deep-links `#/sources/book/:slug`, `#/sources/scholar/:slug`, `#/sources/fatwa` tab switch).
- **Book dialog:** arch cover band + `CatalogRow` ledger (author/subject/school/OCR via `OcrStatusTag`) + inner tabs:
  - `overview` — prose + `requestOcr` note pointing at a nonexistent `Admin → Upload PDF`;
  - `pages` — **placeholder**: `ManuscriptPanel` dashed grid + `OCR pipeline status: {ocrStatus}` (Book dialog is the designated future page-viewer host);
  - `citation` — `CitationBlock` + clipboard copy.
- **Scholar dialog:** arch header, badges, `biographyEn`, linked books → `book/:slug`, `scholarlyViews` with individual-view warning.
- **Fatwa cards:** question/answer, `VerificationBadge`, book/scholar link, volume/page, `TBD`→`requestOcr` badge (display only).
- Supporting primitives (`src/components/platform/architectural.tsx`, `badges.tsx`, `share-bar.tsx`, `detail-chrome.tsx`, `article-toc.tsx`, `related-research.tsx`, `library.tsx`): `ManuscriptPanel/BookSpine/AyahMedallion/NicheMarker/CatalogRow/CitationBlock/EmptyState/DomeLoader`, icon-safe status badges (never color-alone), compact `ShareBar` (Copy Citation/Link [+Print]), reading chrome (progress/breadcrumb/TOC/related). **All reusable for book pages without new design language.**
- Bookmarks support 5 kinds only (`misconception|objection|comparison|question|claim`, `src/lib/bookmarks.ts`) — no `book` kind; page-level bookmarking would need a kind + route extension.

---

## 9. Existing admin architecture

`src/components/platform/views/admin.tsx` — `AdminView()`, data via `apiAdmin` (`x-admin-key: nur-al-usul-admin`, `src/lib/api.ts:22`).

- **Dashboard** (`GET /api/admin/stats`, no auth, no rate limit): 12-entity counts + workflow cards (pending/AI/published/sensitive/verifiedBooks/`ocrBooks` where `ocrStatus != NOT_STARTED`) + verification breakdown (`Misconception.groupBy`) + `topFeedback` (answers grouped by question, up/down sums, top 5) + recent questions (publish/unpublish → `PATCH resource {entity:"answer"…}`, featured toggle) + recent claims. 12+ count queries per load, no caching.
- **Entity editor** (`src/components/platform/admin-editor.tsx` + `GET/POST/PATCH/DELETE /api/admin/resource`): 10 entities (`misconception|objection|book|scholar|fatwa|question|claim|hadith|quran|comparison`) — **notably absent: `Topic, Category, SearchDocument, SearchLog, BookPage, QuestionSuggestion`**. Writes require the admin key (`:36`); **GET is unauthenticated**. Generic passthrough (no schema validation), auto-slug for `misconception|book|scholar`, `take: 100` fixed, single-record ops, bulk select/delete + bulk "Set status" for question/claim/misconception/fatwa, per-row vote badges + `newest|disputed|helpful` sort for questions, `PAGE_SIZE=15` client pagination.
- **Bank tools** (`bank-admin.tsx` + `admin/analytics|duplicates|suggest-questions`): demand signals (`zeroResult` searches, intent mix), duplicate check (token-overlap heuristic, `isCommon` subset ≤1000), AI suggestion queue (max 8/call, approve → `Question PENDING`). **Auth gaps (verified):** `suggest-questions` POST has rate limit but no admin key; `analytics`/`duplicates`/`stats` GETs have neither.
- **Book-ingest fit:** admin is the correct host (gating + workflow cards + editor already exist). Missing: any upload/ingest section, `BookPage` entity management, `SearchDocument` visibility, per-book ingest progress metrics.

---

## 10. Existing SSE architecture

One pattern, two producers, shared client parser.

- **Server:** `answers/stream` + `claims/stream` return `200 text/event-stream` (`Cache-Control: no-cache, no-transform`, `Connection: keep-alive`, `X-Accel-Buffering: no`) with `event: status|delta|done|error` + `data: JSON`. Non-stream errors use `Response.json`. Stream-internal failures arrive as `error` events (no HTTP status change possible mid-stream).
- **Client:** `parseSseFrame` (split on `\n\n`, `event:`/`data:` lines) + `LiveStreamPanel` (stage stepper, auto-scroll, `##` heading styling, `aria-live`) in `views/qa.tsx` (generalized, reused by `views/claims.tsx` with `VERIFY_STEPS`).
- **SDK framing:** `llm-stream.ts` consumes OpenAI-style `data: {choices:[{delta:{content}|message:{content}}]}` / `[DONE]` frames from `z-ai-web-dev-sdk` `stream:true`. A book-ingest progress stream (job status, not LLM tokens) would reuse the HTTP/SSE envelope + `LiveStreamPanel` stepper UX, but needs its own event vocabulary (`queued|extracting|storing|indexing|done`) — not the LLM `delta` path.

---

## 11. Exact integration points (no new app, no parallel systems)

| # | Integration point | File(s) | What attaches there |
|---|---|---|---|
| IP-1 | Admin ingest section | `views/admin.tsx` (new `<BookIngest/>` card between `BankAdminTools` and `EntityEditor`), `apiAdmin` client | PDF upload → job status → OCR review queue; feeds existing `verifiedBooks/ocrBooks` workflow cards |
| IP-2 | Book dialog `pages` tab | `views/sources.tsx` (replace dashed `ManuscriptPanel` placeholder) | Upload → per-page OCR progress → page list/viewer for that `bookId` |
| IP-3 | Book entity definition | `components/platform/admin-editor.tsx` (`book` `FieldDef`s) | Add `volumes/authorId/slug/ocrStatus` (+ file ref) fields so ingested books are immediately editable |
| IP-4 | Fatwa `TBD/requestOcr` badge | `views/sources.tsx` fatwa cards | Deep-link into IP-1/IP-2 scoped to that `book/volume/page` |
| IP-5 | `OcrAttach` pattern | `components/platform/ocr-attach.tsx` | Reuse single-image upload/extract UX for page verification; do NOT force multi-page batch into `ask.tsx` |
| IP-6 | Retrieval enrichment | `src/lib/retrieval.ts:61-92` | New `BOOK_PAGE` branch joining `BookPage→Book` (mirrors existing `BOOK` branch) |
| IP-7 | `SearchDocument` writer | NEW module called by ingest routes (none exists) | Upsert page chunks (`entityType:"BOOK_PAGE"`, `route:"#/sources/book/:slug"` + page anchor) |
| IP-8 | Answer/claim prompts + parsers | `answers/generate`, `answers/stream`, `claims/stream` + `src/lib/ai.ts` | Page-citation support (`[B]` bullets with volume/page, parser → `Citation.bookPageId`); no new answering layer |
| IP-9 | Rate-limit scopes | `src/lib/rate-limit.ts` | New scopes for ingest endpoints (bulk-safe, service-keyed — not per-IP 6/min) |
| IP-10 | `SearchLog.zeroResult` | `admin/analytics` | Demand signal prioritizing which books/pages to ingest first |
| IP-11 | `Review` trail | `Review` model (`targetType:"BOOK_PAGE"` convention) | Page-verification audit without schema change |
| IP-12 | Progress streaming | SSE envelope + `LiveStreamPanel` | Job-status events for long ingests (new vocabulary, same transport) |

---

## 12. Schema changes actually required (minimal, SQLite-convention)

1. **`SearchDocument`: add `@@unique([entityType, entityId])`** — required for any safe upsert-based indexer (current `@@index([entityType])`-only allows duplicates). Needs a one-time dedupe migration (seed writes could have duplicated rows).
2. **`BookPage`: add `language String?`, `engine String?`, `checksum String?`, `status String @default("DONE")`** — all nullable/additive; `status` tracks per-page pipeline state (`QUEUED|OCR_DONE|INDEXED|NEEDS_REVIEW|FAILED`) without overloading `verified`. (`volume/pageNumber/chapter/ocrText/ocrConfidence/imageUrl/verified` already suffice otherwise.)
3. **`Book`: add `sourceRef String?`** (optional; file/object key or origin note for the ingested PDF). `ocrStatus` transitions (`NOT_STARTED→IN_PROGRESS→DONE|NEEDS_REVIEW`) need conventions only, no schema change.
4. **Optional (defer):** `@@index([bookId])` on `BookPage` (covered in practice by the composite unique), `@@index([entityId])` on `SearchDocument`, `targetType "BOOK_PAGE"` convention on `Review` (no DDL).
5. **Explicitly NOT required:** no new models, no chunk table (concatenate or split via `pageNumber` until proven insufficient), no embedding columns (no vector search exists), no enum types (SQLite convention = String), no FK from `SearchDocument` (keep opaque `entityId` pattern).

---

## 13. New backend routes actually required (all under existing `src/app/api/`)

| Route | Method | Purpose | Key notes |
|---|---|---|---|
| `/api/admin/ingest` | `POST` (multipart or JSON job spec) | Accept PDF/page-images, create `Book` (+ placeholder `BookPage`s), enqueue/perform OCR | MUST require `x-admin-key` (unlike some current admin GETs); needs bulk-safe rate scope, not per-IP 6/min |
| `/api/admin/ingest` | `GET ?jobId=` / `?bookId=` | Job/page progress for IP-1/IP-2 UI | Backed by `Book.ocrStatus` + `BookPage.status`; no new job table until async workers exist |
| `/api/admin/pages` | `GET/POST/PATCH/DELETE` | `BookPage` CRUD (read a page, correct `ocrText`, set `verified`, retry one page) | Extends the `admin/resource` pattern; single-page `POST /api/ocr` stays the extraction worker |
| `/api/admin/reindex` | `POST {bookId}` | Rebuild that book's `SearchDocument` rows from `BookPage`s | Idempotent; depends on §12.1 unique; the missing runtime indexer |

**Reuse, don't rebuild:** `POST /api/ocr` (per-page extraction worker, unchanged contract), `GET /api/books` (+ add pagination/`take` cap while there), `GET /api/search` + `retrieveEvidence` (unchanged until page volume forces §16 work), `admin/resource` (add `bookpage` entity mapping instead of a parallel CRUD).

---

## 14. New Python components actually required

**Today: none exist and none are strictly required for v1.** The current OCR engine is the Z-AI vision SDK called from a Next.js route; a same-stack ingest (Next.js route → `POST /api/ocr` per page → Prisma writes) works without Python.

Python becomes justified only if/when: (a) PDF rasterization at scale is needed (pdfplumber/PyMuPDF + Tesseractudier local OCR to cut per-page LLM cost), (b) Arabic-script preprocessing (orthographic normalization, line segmentation) outgrows JS, or (c) batch throughput exceeds serverless/standalone timeouts. If introduced: **one** worker under the existing empty `mini-services/` (e.g. `mini-services/ocr-worker/` with explicit contract: input `{jobId, bookId, pageNumber, imageRef}`, output `{ocrText, confidence, language}` written via the Next.js API, never direct DB access from Python), reusing `tests/python-runtime-*.sh` harness conventions. **Do not** create a parallel search/embedding/RAG stack in Python — retrieval stays in `retrieval.ts` until a vector-search decision is explicitly made.

---

## 15. Frontend changes actually required

1. **`views/admin.tsx`**: new `<BookIngest/>` section (IP-1) — upload control, job list w/ status, review queue entry; wire counts into existing `verifiedBooks/ocrBooks` cards. No new route/view.
2. **`views/sources.tsx`**: replace `pages`-tab placeholder with page list + viewer + per-page verify/retry (IP-2); add ingest entry button on `books` tab header/empty-state; wire fatwa `requestOcr` badges to IP-1 (IP-4).
3. **`admin-editor.tsx`**: extend `book` fields (IP-3); add `bookpage` entity (search, pagination, row-click edit, verify toggle) reusing `EntityForm`/bulk patterns.
4. **`retrieval.ts` consumers need no UI change**; when `BOOK_PAGE` results flow, `search.tsx` type chips should include the new type and `openHit` should route `#/sources/book/:slug` (+page anchor).
5. **`library.tsx`**: optional `book` kind (route `#/sources/book/:slug`) if page/book bookmarking is wanted; else defer.
6. **i18n**: every new string needs EN/UR/AR keys (`src/lib/i18n.ts`); RTL + dark-mode + 390px checks per existing convention.
7. **Explicitly not needed:** no new top-level view, no separate book app, no new design language (reuse `ManuscriptPanel/BookSpine/EmptyState/DomeLoader/CitationBlock`), no new SSE client (reuse `LiveStreamPanel`).

---

## 16. Risks

| # | Risk | Severity | Mitigation |
|---|---|---|---|
| R-1 | `SearchDocument` unbounded growth breaks search (`take:500`) + retrieval (`take:400`) — silent truncation, linear JS scans, weight-bias | **High** | Scope ingest indexing (top books first via `zeroResult` demand); add pagination/cursor + SQL-side `where` before bulk index; document the ceiling in the ingest UI |
| R-2 | `@@unique([bookId,volume,pageNumber])` violations on re-ingest / multi-volume PDFs with irregular numbering | High | Normalize volume/page to Int at job creation; idempotent upsert keyed on the triple; pre-validate numbering before OCR spend |
| R-3 | Duplicate `SearchDocument` rows (no unique today) divergently indexed | High | §12.1 unique + dedupe migration before first bulk index |
| R-4 | OCR cost/latency per page (vision LLM) × thousands of pages; 6/min/IP throttle | High | Service-scoped limits (§13); batch during off-peak; Python/Tesseract tier for clean prints (§14) reserving vision OCR for difficult pages |
| R-5 | OCR quality on Nastaliq/diacritics/footnotes → substring retrieval misses (no Arabic normalization, no stemming) | Medium | Arabic orthographic normalization in tokenizer + `SearchDocument.body` builder; surface `ocrConfidence`/`verified` in ranking weight later |
| R-6 | `db.ts log:['query']` floods logs on bulk writes | Medium | Gate query logging to non-production or sample it before ingest work |
| R-7 | Unauthenticated admin GETs (`stats/analytics/resource-GET/suggest-PATCH`) + weak shared key on writes | Medium | Require key on all admin routes before exposing ingest; rotate key out of source (`src/lib/api.ts:22` hardcodes it) into env |
| R-8 | SQLite concurrency (single-file, Prisma) under parallel page writes | Medium | Serialize page writes per job (or WAL mode); keep transactions small; plan PostgreSQL swap path per schema header |
| R-9 | `imageUrl` has no storage backend (S3/local convention undefined); `db/custom.db` and `download/*.png` suggest ad-hoc artifacts | Medium | Define one convention (local `public/uploads` vs object storage) before storing page images; never commit scans to git |
| R-10 | Answer/stream parser drift (omitted `laterEvidence/disputed`, `classicalEvidence` fallback bucket) will misfile page citations | Medium | Extend parsers + add fixtures when `[B]` bullets land; keep generate/stream schemas in lockstep |
| R-11 | Non-canonical folder (`Nur al asul process/`) diverging or being pushed to the same `origin` | Medium | Archive/delete or repoint; never dual-edit (§0) |
| R-12 | `.env` is tracked in git (verified: `M .env` appeared in status pre-`fileMode` fix) | Low-Med | Untrack + rotate any exposed secrets; keep `DATABASE_URL` local-only going forward |

---

## 17. Migration strategy

1. **Freeze + decide (§0):** confirm `Nul al usal front/` canonical; archive/repoint the other folder. No code changes yet.
2. **Secrets + access hygiene (no DDL):** untrack `.env`, rotate exposed values; move admin key to env; gate admin GETs. (Fixes R-7/R-12 before new attack surface.)
3. **DDL migration (additive only):** `SearchDocument @@unique([entityType,entityId])` after a dedupe script; `BookPage += language/engine/checksum/status`; `Book += sourceRef`. Regenerate client, `db:push`/migrate. Nothing existing is renamed or dropped.
4. **Indexer + routes:** add `SearchDocument` writer module; ship `/api/admin/pages` + `/api/admin/reindex` first (pages become correctable and searchable), then `/api/admin/ingest` (upload → `BookPage` rows via existing `POST /api/ocr` per page → index).
5. **Retrieval enablement:** add the `BOOK_PAGE` enrichment branch + prompt/parser page-citation support; backfill `SearchDocument` for already-ingested books via `reindex`.
6. **UI:** admin ingest section → source `pages` tab → editor fields → search/bookmark wiring; trilingual keys throughout.
7. **Pilot:** ingest 1–3 high-demand books (chosen from `zeroResult` analytics), verify OCR→verify→search→RAG-answer loop end-to-end, measure `take:400/500` headroom, then scale.
8. **Scale decision point:** if page volume approaches the in-memory ceilings, rework search/retrieval SQL-side (pagination, `where` pushdown, FTS — e.g. SQLite FTS5 virtual table alongside, still no new system) before further bulk ingest.

---

## 18. What must NOT be changed

1. **No new AI answering layer.** `answers/generate`, `answers/stream`, `claims`, `claims/stream`, `ai.ts`, `llm-stream.ts`, `ANTI_HALLUCINATION_RULES` stay the single answering stack; page grounding extends prompts/parsers only.
2. **No parallel search/RAG system.** No Python/JS duplicate of `GET /api/search` or `retrieveEvidence`; no vector store until an explicit architectural decision supersedes this audit.
3. **No `POST /api/ocr` contract change.** Single-image `{imageBase64, mimeType}` in/out stays stable — it is the per-page worker and the Ask-flow dependency (`ocr-attach.tsx`). Extend *around* it (batch caller, rate scope), not inside it.
4. **No schema renames/drops.** Additive columns/unique only. `BookPage @@unique([bookId,volume,pageNumber])`, `Citation`'s optional-FK shape, `Review`'s polymorphic shape, and the SQLite String-for-enum/JSON convention are load-bearing — preserve them.
5. **No new top-level view or separate app.** All book UI lives in `#/sources`, `#/admin`, and the existing editor/dialog components.
6. **No auth weakening.** Nothing in the ingest surface ships without the admin key (and its move to env); existing open admin GETs must be tightened, not mirrored.
7. **No Caddy header stripping.** `X-Forwarded-For`/`X-Real-IP` passthrough feeds `rateLimitByIp` — preserve it.
8. **No edits in the non-canonical folder.** All work in `Nul al usal front/` only.
9. **No seed-data fabrication.** The anti-hallucination policy (only established citations ship `VERIFIED`; uncertain pages/gradings stay `UNVERIFIED`/NULL) applies equally to ingested OCR content: low-confidence pages enter as `NEEDS_REVIEW`, never as verified evidence.

---

## Appendix A. Baseline checks (run 2026-09-27, canonical root)

| Check | Command | Result |
|---|---|---|
| ESLint | `bun run lint` (`eslint .`) | **Cannot run — dependencies not installed:** `node_modules/` does not exist in this checkout, so the `eslint` binary is absent (`bun: command not found: eslint`). Not an app-code finding. Rerun after `bun install`. (Toolchain present: Bun 1.3.14, Node v24.18.0.) |
| Unit tests | — | **None exist.** `tests/` holds only deploy-harness shell scripts (`database-runtime-build.sh`, `python-runtime-build.sh`, `python-runtime-container.sh`); no vitest/jest/playwright suites. Nothing to run. |
| Type check | — | Not run (repo sets `typescript.ignoreBuildErrors: true`; no `typecheck` script in `package.json`). |
| Folder parity | SHA-256 compare (excl. `.git/node_modules/.next`) | Identical except `README.md` (canonical only) + `.zscripts/dev.pid` (ephemeral). See §0. |
| `db.bookPage` refs in `src/` | repo grep | **Zero** — confirms §2/§6. |
| `SearchDocument` writers in `src/` | repo grep | **Zero** — seeds only (`seed.ts:834`, `seed-bank.ts:350`). Confirms §6. |

## Appendix B. Key file map (all paths relative to canonical root)

`prisma/schema.prisma` · `prisma/seed.ts` · `prisma/seed-bank.ts` · `src/lib/db.ts` · `src/lib/retrieval.ts` · `src/lib/ai.ts` · `src/lib/llm-stream.ts` · `src/lib/rate-limit.ts` · `src/lib/cite.ts` · `src/lib/store.ts` · `src/lib/api.ts` · `src/lib/i18n.ts` · `src/lib/bookmarks.ts` · `src/app/page.tsx` · `src/app/api/ocr/route.ts` · `src/app/api/books/route.ts` · `src/app/api/search/route.ts` · `src/app/api/answers/generate/route.ts` · `src/app/api/answers/stream/route.ts` · `src/app/api/answers/feedback/route.ts` · `src/app/api/claims/route.ts` · `src/app/api/claims/stream/route.ts` · `src/app/api/admin/stats/route.ts` · `src/app/api/admin/resource/route.ts` · `src/app/api/admin/analytics/route.ts` · `src/app/api/admin/duplicates/route.ts` · `src/app/api/admin/suggest-questions/route.ts` · `src/components/platform/views/sources.tsx` · `src/components/platform/views/search.tsx` · `src/components/platform/views/ask.tsx` · `src/components/platform/views/qa.tsx` · `src/components/platform/views/admin.tsx` · `src/components/platform/ocr-attach.tsx` · `src/components/platform/admin-editor.tsx` · `src/components/platform/bank-admin.tsx` · `package.json` · `bun.lock` · `next.config.ts` · `Caddyfile` · `mini-services/` (empty) · `scripts/gen-depth-translations.ts` · `scripts/gen-icons.py` · `tests/*.sh` · `worklog.md`
