# Search & Retrieval Integration — Phase 5 Deliverable

> Processed books are now a first-class source family in the EXISTING search
> and RAG systems. No second search system, no new database technology
> (Prisma + SQLite preserved). Audit reference: §5/§6.

## 1. What changed (canonical root only)

| File | Change |
|---|---|
| `prisma/schema.prisma` | `SearchDocument` += `volume Int?`, `pageNumber Int?` (queryable jild/page keys; `meta` stays the record) |
| `src/lib/search-score.ts` | NEW pure scorer: exact + normalized + phrase + filters + snippets + provenance attach |
| `src/lib/semantic.ts` | NEW `SemanticProvider` abstraction + `TfidfProvider` + `rerank()` |
| `src/app/api/search/route.ts` | Rewritten onto the scorer; +`bookId`, `volume`, `semantic` params; +book provenance in results |
| `src/lib/retrieval.ts` | bodySearch backstop bonus (+1, elif-style); BOOK_PAGE enrichment was Phase 4 |
| `src/app/api/admin/reindex/route.ts` | Populates `volume`/`pageNumber` columns |
| `src/lib/api.ts` | `SearchHit.provenance?` (additive) |
| `src/lib/ai.client.ts` | `BOOK_PAGE: Book passage` label |
| `src/lib/i18n.ts` | `bookPassages` key × EN/UR/AR |
| `src/components/platform/views/search.tsx` | Passages chip + provenance line under book hits (`openHit` already deep-linked books) |

## 2. Ranking behavior (read before modifying — preserved by contract)

- Legacy algorithm kept EXACTLY for rows without `bodySearch`: per term
  title +4 elif body +2, typo prefix floor 1.5, filter >0, stable desc,
  top 30, `body.slice(0,220)` snippet, soft lang filter, searchLog write.
  Proven by hand-computed assertions (tawassul = 4, remembrance = 2,
  remembrancex = 1.5) in `tests/search-score.test.ts`.
- `bodySearch` contributes only via a further elif (+2): folded Urdu/Arabic
  variants match without double-counting. Old rows (`bodySearch` NULL) score
  byte-identically — proven by live-DB assertions (11.2, 8 exact).
- Retrieval: same elif discipline (+1 backstop on folded terms). Old rows
  keep identical scores; only `bodySearch`-carrying rows can gain.
- Seed weights (1–1.4) vs reindex weight 1: same tier, no truncation bias at
  current corpus size (400/500 caps documented, unbinding).

## 3. New capabilities

- **Normalized search**: Urdu-variant queries fold onto the folded index
  (میلاد example asserted both sides: TS scorer + Python normalizer).
- **Phrase search**: `"..."` (≤3) required + 6 each; snippet centers on the
  first phrase hit (ellipsis-prefixed when offset).
- **Metadata filtering**: `type` restricts all families; `bookId`/`volume`
  scope ONLY `BOOK_PAGE` rows (other families pass through — filters narrow
  books, never hide the library). Jild filtering = `volume` (queryable
  column, not JSON LIKE).
- **Provenance** on every book hit: book title/slug, author, volume, chapter,
  page, pageId, docId, verified flag — rendered in UI, routed to the existing
  book dialog.
- **Semantic abstraction**: `SemanticProvider.score()` (async, forward-
  compatible with embedding backends incl. a future sqlite-vec swap with zero
  caller changes) + dependency-free TF-IDF cosine + `rerank()` blend
  (default weight 3 ≈ one title-term). Opt-in `?semantic=1` (top-50 rerank);
  default ranking untouched.

## 4. Validation (run 2026-09-27)

| Check | Result |
|---|---|
| bun `tests/` (5 files) | **49 pass / 0 fail**: scorer legacy-exactness, normalized backstop (no double-count), phrases, bookId/volume scoping, provenance attach + null-safety, semantic cosine/TF-IDF/rerank, i18n-intact suites |
| pytest worker suite | unaffected (no worker changes); מילאד fold test added, normalize file green |
| Live retrieval vs scratch SQLite (real Prisma stack) | **6 pass**: misconception 11.2 + CLAIM body, quran 8.0 exact, BOOK enrichment intact, BOOK_PAGE excerpt with vol.4/p.112/chapter/unverified label, Urdu-fold hit = 1.0, old scores stable with books present |
| Prisma validate/generate/push | valid; client regenerated (fixes stale-client `volume` rejection found by the tests); push to scratch OK |
| Route-level HTTP (search params, reindex, provenance JSON) | deferred — needs `next/server` (node_modules has only the Prisma client); logic covered via scorer/provenance unit tests + retrieval integration |
| Full-book / production corpus | out of scope (Phase 4 stop rule stands) |

## 5. Known limits / next hooks

- `take:400/500` weight-desc caps predate this phase; revisit when book docs
  approach them (SQL-side pushdown, not a new system).
- `section` in provenance is null (lives in `meta` only) — surface when the
  book dialog gains page anchors (`#/sources/book/{slug}` works today).
- Semantic rerank is opt-in; promoting it to default needs an A/B pass over
  the seeded corpus first.
- `?volume=` validates positive-int (400 otherwise); unknown `type` yields
  empty (pre-existing semantics kept).
