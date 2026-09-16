# Verification, Metadata, Chunking & Indexing — Phase 4 Deliverable

> Extracted/OCR text becomes searchable, structured knowledge. No second
> search model, no second database, no parallel AI layer.
> Audit reference: `docs/BOOK_PIPELINE_INTEGRATION_AUDIT.md` §5/§6/§12.

## 1. Provenance (never lost)

Every chunk carries: `bookId → Book`, volume, chapter, section, pageNumber,
pdfPage, pageId (`BookPage.id`), jobId, engine, model (+model_version),
checksum, language. Path: worker `PageResult/metadata` → writeback
(`signals.cues`) → `BookPage.signals` → `POST /api/admin/reindex` merges cues
into `SearchDocument.meta` (whitelisted keys). Retrieval's new `BOOK_PAGE`
branch (`src/lib/retrieval.ts`) renders volume/page + verified-vs-OCR state
into the AI prompt. Verified end-to-end on both samples (book, jild, page,
text, language, doc, provenance all asserted).

## 2. Text states (RAW / NORMALIZED / VERIFIED)

- `BookPage.ocrText` = RAW. Fresh re-OCR may replace it; corrections never
  touch it. No per-revision history (documented limitation).
- `BookPage.normalizedText` = search-safe variant (worker-computed).
- `BookPage.verifiedText` = human correction via `PATCH …/pages {verify}`.
- Display everywhere = `verifiedText ?? ocrText`. Index `body` = same;
  `bodySearch` = normalized. Retrieval prefers `verifiedText`.

## 3. Metadata (cues only — unknowns stay NULL)

`mini-services/ocr-worker/metadata.py`: chapter/section headings; Tafsir
surah (`سور…` + name), ayahStart/End (ranges incl. الی/تا), juz (پارہ/جزء),
ruku; Fatawa jild, masala (+required number), سوال/جواب offsets (into the
folded string — folds are 1:1 so offsets hold). Detection runs on
`fold_variants()` (NFC + Urdu folds, offset-preserving). All literals are
`\u` escapes (homoglyph-safe); OCR realities handled: dropped word-final
heh (`مسئل\S?` + required number), reh/lam confusion (`nmbr|nmbl`),
0649 final-yeh. Never invents: abs patterns → None.

## 4. Verification signals (`verify.py` → `BookPage.signals` JSON)

ocrConfidence, lowConfRatio, engineDisagreement (embedded-vs-OCR overlap on
MIXED pages), scriptConfidence, unicodeAnomalies (private-use, odd Arabic
format chars, stacked combining), lexiconScore (ur/ar/en function words),
layoutFlags (overlap, height spread, no-lines), structuralFlags, verdict
OK/REVIEW + reasons. REVIEW (or HANDWRITTEN) → writeback sets NEEDS_REVIEW
instead of OCR_DONE. Text is flagged, never corrected.

## 5. Chunking (`structure.py`)

Default indexed unit = PAGE (physical, provenance-exact, never splits
unrelated text). `split_paragraphs()` (+offsets) and `find_quotations()`
(quote marks, ۝ verses) available for long pages; paragraph children inherit
full provenance. `chunk_page()` always emits the page chunk first.

## 6. SearchDocument (extended, not duplicated)

`+ bodySearch` (index text), `+ bookId` (`@@index`), `+ meta` (provenance
JSON), `+ @@unique([entityType,entityId])` (idempotent reindex). `/api/search`
picks up `BOOK_PAGE` rows with zero changes (it scans the table directly);
retrieval enrichment gained the `BOOK_PAGE` branch. `POST /api/admin/reindex
{bookId}`: delete book docs → create one doc/page (OCR_DONE + NEEDS_REVIEW
with text; skips empty/pending/failed) → flips OCR_DONE→INDEXED. Deploys on
existing SQLite: `db push` needs a one-time dupe cleanup if rerun over dirty
data (seeds delete-first, so clean seeds are safe).

## 7. Search normalization (display ⊥ index)

`normalizeSearchText` (TS) / `normalize_text` (Python), same rules: NFC,
kashida removal, alef folding, tashkeel strip (optional, kept for Quranic
display parity), Urdu folds 06CC/0649→064A + 06C3→0629. Teh-marbuta/heh never
folded. Rationale (verified): EasyOCR emits Arabic forms for Urdu input, so
both index and query sides fold identically. `guessLanguage` AR/UR/EN aligns
with RAG + worker detectors (explicit escapes; pre-existing retrieval.ts set
verified correct).

## 8. Validation (run 2026-09-27)

| Check | Result |
|---|---|
| pytest full worker suite | **51 passed / 0 fail** (router, preprocess, normalize+folds, engines incl. HTR separation, API contract, metadata, structure, verify, samples, indexing chains) |
| bun tests (`search-normalize` + `book-processing`) | **22 passed / 0 fail** |
| Fatawa Razvia sample (scan) | route SCANNED, jild=4, masala=112, Q/A spans, chapter; doc shape + provenance asserted |
| Tibyan sample (scan) | surah=البقرۃ, ayah 2–2, ruku=1, doc shape + provenance asserted |
| Known model gaps (pinned, not hidden) | Urdu peh→yeh (juz cue lost), dropped word-final heh (tolerated), digits/Latin exact; full list §9 |
| Prisma validate/generate/push (scratch) | valid; client regen; push OK; round-trip: bookId query (1 doc), unique enforced (dup rejected), RAW kept across verify, cascade delete (0 left). Scratch removed |
| ESLint / live-server round-trip | still blocked (deps) / checklist in §10 |

## 9. Verified OCR behavior log (EasyOCR 1.7.2, synthetic Naskh scans)

- Emits Arabic codepoints for Urdu input (06CC→064A, 06C3→0629, final-yeh→0649) → folded at index; display verbatim.
- Preserves 06A9 (keheh) correctly — no fold.
- Drops word-final heh/marbuta occasionally → tolerated in masala pattern (number required).
- Confuses reh/lam at small sizes → tolerated in nmbr group (number required).
- Splits same-line words into separate detections → height-relative row merge (0.6× median) + RTL ordering fixed marker adjacency.
- RTL ordering bug found: engine defaulted LTR when "en" in lang set → now RTL unless hint is exactly "en".
- Arabic-script literals in source are homoglyph-prone (ب/ں, ی/ي/ى, ۃ/ة, ک/ک): all pipeline literals are `\u` escapes; test expectations use `fold_variants()` wrapping; lesson recorded.

## 10. Live-server checklist (needs Next.js + DB)

1. `bun install`, scratch DB, push + seed.
2. Create Book + job with totalPages; run worker `--limit 2` (real writeback: OCR_DONE/NEEDS_REVIEW rows, counters refresh).
3. `POST /api/admin/reindex` → docs present; `GET /api/search?q=` hits them; `retrieveEvidence` returns BOOK_PAGE bodies with provenance.
4. `verify` with verifiedText → display + RAG prefer it; RAW unchanged.
5. `retry` → resume skips INDEXED pages.

## 11. Stopping point

Indexing loop closes at reindex; admin UI (ingest section, pages viewer) and
bulk-book runs remain future work. No full-book processing until the
sample→review→index loop is validated live (per brief).
