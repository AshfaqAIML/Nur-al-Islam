import { NextRequest, NextResponse } from "next/server";
import { db } from "@/lib/db";
import { attachProvenance, scoreDocuments } from "@/lib/search-score";
import { rerank } from "@/lib/semantic";

/**
 * Search-intent classification (Common Questions Library spec):
 * informational | fiqh | misconception | evidence | source-lookup.
 * Heuristic-first; every search is logged for the admin analytics loop.
 */
export function classifyIntent(q: string): string {
  const t = q.toLowerCase();
  if (/(show me|find|quote from|open|page of|volume of|radd al-muhtar on|hidayah on|fatawa razvia on|where in)/.test(t)) return "source-lookup";
  if (/(proof|daleel|evidence|cite|citation|source|which hadith|what hadith|verse)/.test(t)) return "evidence";
  if (/(is it true|do hanafis reject|don'?t hanafis|hanafis don'?t|myth|misconception|really|right\?|shirk\?|bid'?ah\?|reject hadith|blind)/.test(t)) return "misconception";
  if (/(ruling|hukm|halal|haram|valid|invalid|break|wajib|fard|can i|do i|should i|permissible|makruh|how do|how many|when do)/.test(t)) return "fiqh";
  return "informational";
}

/**
 * Unified search across the SearchDocument index — Phase 5.
 * Ranking math lives in src/lib/search-score.ts (unit-tested); this handler
 * keeps HTTP/DB/logging. Query params:
 *   q (required) · type (entityType) · lang · surface
 *   bookId — scopes BOOK_PAGE hits to one book (other families pass through)
 *   volume — scopes BOOK_PAGE hits to one jild/volume (others pass through)
 *   semantic=1 — opt-in TF-IDF cosine rerank (default ranking unchanged)
 */
export async function GET(req: NextRequest) {
  const sp = req.nextUrl.searchParams;
  const q = (sp.get("q") ?? "").trim();
  const type = sp.get("type");
  const lang = sp.get("lang");
  const surface = sp.get("surface") ?? "search";
  const bookId = sp.get("bookId");
  const volumeRaw = sp.get("volume");
  const semantic = sp.get("semantic") === "1";
  const volume = volumeRaw !== null && volumeRaw !== "" ? Number(volumeRaw) : null;

  if (!q) {
    return NextResponse.json({ results: [], query: q, intent: null });
  }
  if (volume !== null && (!Number.isInteger(volume) || volume < 1)) {
    return NextResponse.json({ error: "volume must be a positive integer" }, { status: 400 });
  }

  const intent = classifyIntent(q);

  // Candidate fetch: type restricts all families; bookId/volume scope only
  // BOOK_PAGE rows (other families have no book columns and pass through).
  const where: Record<string, unknown> = {};
  const and: Record<string, unknown>[] = [];
  if (type) where.entityType = type;
  if (bookId) {
    and.push({ OR: [{ entityType: { not: "BOOK_PAGE" } }, { entityType: "BOOK_PAGE", bookId }] });
  }
  if (volume !== null) {
    and.push({ OR: [{ entityType: { not: "BOOK_PAGE" } }, { entityType: "BOOK_PAGE", volume }] });
  }
  if (and.length > 0) where.AND = and;

  const candidates = await db.searchDocument.findMany({
    where,
    take: 500,
    orderBy: { weight: "desc" },
  });

  let scored = scoreDocuments(candidates, q, {
    type,
    bookId,
    volume,
  });
  if (semantic) {
    scored = await rerank(scored.slice(0, 50), q).then((r) => r.slice(0, 30));
  }

  // Language filter (multilingual search: searching "توسل" should find Tawassul)
  let results = scored;
  if (lang) {
    const langFiltered = results.filter((d) => d.language === lang);
    if (langFiltered.length > 0) results = langFiltered;
  }

  // Book provenance for passage hits (two batched queries, any family size).
  const withProv = await attachProvenance(results, async (pageIds) => {
    const pages = await db.bookPage.findMany({
      where: { id: { in: pageIds } },
      select: {
        id: true, volume: true, pageNumber: true, chapter: true, verified: true,
        book: { select: { id: true, titleEn: true, slug: true, author: { select: { nameEn: true } } } },
      },
    });
    return new Map(pages.map((p) => [p.id, p]));
  });

  // Analytics log (fire-and-forget; no IP stored — aggregate signal only)
  db.searchLog
    .create({
      data: {
        query: q.slice(0, 300),
        results: withProv.length,
        intent,
        language: (lang ?? "EN").toUpperCase().slice(0, 2),
        surface: surface.slice(0, 20),
      },
    })
    .catch(() => {});

  return NextResponse.json({
    query: q,
    intent,
    count: withProv.length,
    results: withProv.map((r) => ({
      entityType: r.entityType,
      entityId: r.entityId,
      title: r.title,
      titleUr: r.titleUr,
      titleAr: r.titleAr,
      snippet: r.snippet,
      route: r.route,
      score: Math.round(r.score * 10) / 10,
      provenance: r.provenance,
    })),
  });
}
