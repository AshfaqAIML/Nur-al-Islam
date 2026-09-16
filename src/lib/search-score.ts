/**
 * Pure search scoring shared by GET /api/search (Phase 5).
 *
 * Extracted 1:1 from the route so the ranking is unit-testable; the route
 * keeps HTTP/DB/logging, this module keeps the math. Backward-compatibility
 * contract (asserted in tests/search-score.test.ts):
 * - documents WITHOUT bodySearch score EXACTLY as the pre-Phase-5 route
 *   (title +4 elif body +2, typo-tolerant floor 1.5, filter >0, stable
 *   desc sort, top 30, body.slice(0,220) snippet).
 * - bodySearch contributes only via a further elif (+2): normalized
 *   (folded) matches for Urdu/Arabic spelling variants — never double-count.
 * - phrases ("...") are required filters (+6 each) matched against title,
 *   body, or folded bodySearch.
 * - bookId/volume scope ONLY BOOK_PAGE documents; every other family passes
 *   through unfiltered (filters narrow books, never hide the library).
 */
import { normalizeSearchText } from "@/lib/search-normalize";

export interface SearchDocInput {
  id?: string;
  entityType: string;
  entityId: string;
  title: string;
  titleUr?: string | null;
  titleAr?: string | null;
  body: string;
  bodyUr?: string | null;
  bodyAr?: string | null;
  bodySearch?: string | null;
  language?: string | null;
  route: string;
  weight?: number | null;
  bookId?: string | null;
  volume?: number | null;
  pageNumber?: number | null;
}

export interface SearchFilters {
  type?: string | null;
  bookId?: string | null;
  volume?: number | null;
}

export interface ScoredHit extends SearchDocInput {
  score: number;
  snippet: string;
}

export interface BookProvenance {
  bookId: string;
  bookTitle: string;
  bookSlug: string;
  author: string | null;
  volume: number | null;
  chapter: string | null;
  section: string | null;
  page: number | null;
  pageId: string;
  docId: string;
  verified: boolean;
}

export function extractPhrases(q: string): { phrases: string[]; rest: string } {
  const phrases: string[] = [];
  const rest = q.replace(/"([^"]+)"/g, (_, p: string) => {
    const t = p.trim();
    if (t.length > 1 && phrases.length < 3) phrases.push(t);
    return " ";
  });
  return { phrases, rest };
}

export function tokenizeTerms(q: string): string[] {
  return q.toLowerCase().split(/\s+/).filter((t) => t.length > 1).slice(0, 10);
}

function passesFilters(d: SearchDocInput, f: SearchFilters): boolean {
  if (f.type && d.entityType !== f.type) return false;
  if (d.entityType === "BOOK_PAGE") {
    if (f.bookId && d.bookId !== f.bookId) return false;
    if (f.volume !== undefined && f.volume !== null && d.volume !== f.volume) return false;
  }
  return true;
}

export function scoreDocuments(
  docs: SearchDocInput[],
  query: string,
  filters: SearchFilters = {},
  opts: { limit?: number; snippetLen?: number } = {},
): ScoredHit[] {
  const limit = opts.limit ?? 30;
  const snippetLen = opts.snippetLen ?? 220;
  const { phrases, rest } = extractPhrases(query);
  const terms = tokenizeTerms(rest);
  const foldedTerms = tokenizeTerms(normalizeSearchText(rest));
  const foldedPhrases = phrases.map((p) => normalizeSearchText(p).toLowerCase());

  const out: ScoredHit[] = [];
  for (const d of docs) {
    if (!passesFilters(d, filters)) continue;
    const title = `${d.title} ${d.titleUr ?? ""} ${d.titleAr ?? ""}`.toLowerCase();
    const body = `${d.body} ${d.bodyUr ?? ""} ${d.bodyAr ?? ""}`.toLowerCase();
    const searchIx = (d.bodySearch ?? "").toLowerCase();
    const foldedTitle = normalizeSearchText(`${d.title} ${d.titleUr ?? ""} ${d.titleAr ?? ""}`).toLowerCase();

    // Phrases are required: every phrase must occur in title, body, or the
    // folded index (folded comparison covers Urdu spelling variants).
    let phraseBonus = 0;
    let phraseOk = true;
    let firstPhraseAt = -1;
    for (let i = 0; i < phrases.length; i++) {
      const p = phrases[i].toLowerCase();
      const fp = foldedPhrases[i];
      const inTitle = p.length > 0 && title.includes(p);
      const atBody = p.length > 0 ? body.indexOf(p) : -1;
      const inSearch = fp.length > 0 && (searchIx.includes(fp) || foldedTitle.includes(fp));
      if (!inTitle && atBody < 0 && !inSearch) {
        phraseOk = false;
        break;
      }
      phraseBonus += 6;
      if (atBody >= 0 && (firstPhraseAt < 0 || atBody < firstPhraseAt)) firstPhraseAt = atBody;
    }
    if (!phraseOk) continue;

    let score = 0;
    for (const t of terms) {
      if (title.includes(t)) score += 4;
      else if (body.includes(t)) score += 2;
      else if (searchIx.includes(t)) score += 2;
    }
    // Folded-variant terms (e.g. Urdu 06CC query vs 064A index) match the
    // normalized field when the raw term did not already score.
    for (const t of foldedTerms) {
      if (terms.includes(t)) continue;
      if (!title.includes(t) && !body.includes(t) && searchIx.includes(t)) score += 2;
    }
    // Typo tolerance: prefix matching for longer terms (unchanged legacy).
    for (const t of terms) {
      if (t.length > 4 && (title.startsWith(t.slice(0, t.length - 1)) || body.includes(t.slice(0, t.length - 1)))) {
        score = Math.max(score, 1.5);
      }
    }
    score += phraseBonus;
    if (score <= 0) continue;

    let snippet = d.body.slice(0, snippetLen);
    if (firstPhraseAt >= 0) {
      const start = Math.max(0, firstPhraseAt - 60);
      snippet = (start > 0 ? "…" : "") + d.body.slice(start, start + snippetLen);
    }
    out.push({ ...d, score, snippet });
  }
  out.sort((a, b) => b.score - a.score); // stable: ties keep fetch (weight) order
  return out.slice(0, limit);
}

export interface PageFetchRow {
  id: string;
  volume: number;
  pageNumber: number;
  chapter: string | null;
  verified: boolean;
  book: { id: string; titleEn: string; slug: string; author: { nameEn: string } | null } | null;
}

/**
 * Attach book provenance to BOOK_PAGE hits. The fetcher is injected so this
 * stays pure/testable; the route passes a Prisma-backed implementation that
 * batch-loads pages + books + authors in two queries.
 */
export async function attachProvenance<T extends ScoredHit>(
  hits: T[],
  fetchPages: (pageIds: string[]) => Promise<Map<string, PageFetchRow>>,
): Promise<(T & { provenance: BookProvenance | null })[]> {
  const ids = [...new Set(hits.filter((h) => h.entityType === "BOOK_PAGE").map((h) => h.entityId))];
  const rows = ids.length > 0 ? await fetchPages(ids) : new Map<string, PageFetchRow>();
  return hits.map((h) => {
    if (h.entityType !== "BOOK_PAGE") return { ...h, provenance: null };
    const p = rows.get(h.entityId);
    if (!p || !p.book) return { ...h, provenance: null };
    return {
      ...h,
      provenance: {
        bookId: p.book.id,
        bookTitle: p.book.titleEn,
        bookSlug: p.book.slug,
        author: p.book.author?.nameEn ?? null,
        volume: p.volume,
        chapter: p.chapter,
        section: null, // section lives in SearchDocument.meta (Phase 4); surfaced in a follow-up
        page: p.pageNumber,
        pageId: p.id,
        docId: h.id ?? h.entityId,
        verified: p.verified,
      } satisfies BookProvenance,
    };
  });
}
