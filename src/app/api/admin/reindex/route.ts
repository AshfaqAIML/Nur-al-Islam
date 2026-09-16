import { NextRequest, NextResponse } from "next/server";
import { db } from "@/lib/db";
import { rateLimitByIp, tooMany } from "@/lib/rate-limit";
import { guessLanguage, normalizeSearchText } from "@/lib/search-normalize";

/**
 * Book reindex (Phase 4) — populates the EXISTING SearchDocument index.
 *
 * POST { bookId } → rebuilds this book's BOOK_PAGE documents:
 *   1. reads pages with text (OCR_DONE + NEEDS_REVIEW; skips empty/pending/failed)
 *   2. deletes the book's previous BOOK_PAGE docs (idempotent rebuild)
 *   3. creates one document per page: body = display text
 *      (verifiedText ?? ocrText — RAW never mixed with corrections),
 *      bodySearch = normalized index variant, meta = provenance JSON
 *   4. marks OCR_DONE pages INDEXED (NEEDS_REVIEW pages stay flagged but searchable)
 *
 * No new search model. Unknown metadata stays absent — never invented.
 */
import { checkAdmin } from "@/lib/admin-auth";

function pageLanguage(raw: string | null, text: string): string {
  const v = (raw ?? "").toLowerCase();
  if (v === "ar" || v === "ur" || v === "en") return v.toUpperCase();
  return guessLanguage(text);
}

export async function POST(req: NextRequest) {
  const rl = rateLimitByIp(req, "ingest", 30);
  if (!rl.ok) return tooMany(rl.retryAfter);
  if (!checkAdmin(req)) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  let body: { bookId?: string };
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON" }, { status: 400 });
  }
  if (!body.bookId) return NextResponse.json({ error: "bookId is required" }, { status: 400 });
  try {
    const book = await db.book.findUnique({
      where: { id: body.bookId },
      include: { author: { select: { nameEn: true } } },
    });
    if (!book) return NextResponse.json({ error: "Book not found" }, { status: 404 });
    const pages = await db.bookPage.findMany({
      where: { bookId: book.id, status: { in: ["OCR_DONE", "NEEDS_REVIEW"] } },
      orderBy: [{ volume: "asc" }, { pageNumber: "asc" }],
    });
    const withText = pages.filter((p) => (p.verifiedText ?? p.ocrText ?? "").trim().length > 0);
    const latestJob = await db.bookProcessingJob.findFirst({
      where: { bookId: book.id },
      orderBy: { createdAt: "desc" },
      select: { id: true },
    });
    await db.searchDocument.deleteMany({ where: { entityType: "BOOK_PAGE", bookId: book.id } });
    const docs = withText.map((p) => {
      const display = (p.verifiedText ?? p.ocrText ?? "").trim().slice(0, 8000);
      let signals: Record<string, unknown> | null = null;
      try {
        signals = p.signals ? (JSON.parse(p.signals) as Record<string, unknown>) : null;
      } catch {
        signals = null;
      }
      // Phase 4: worker-stored metadata cues (chapter/surah/masala/...) merge
      // into doc meta. Only whitelisted cue keys; unknown stays absent.
      const cues = (signals?.cues ?? {}) as Record<string, unknown>;
      const pick = (k: string) => (k in cues ? cues[k] : null);
      const meta = {
        volume: p.volume,
        pageNumber: p.pageNumber,
        chapter: p.chapter,
        section: pick("section"),
        jild: pick("jild"),
        surah: pick("surah"),
        ayahStart: pick("ayahStart"),
        ayahEnd: pick("ayahEnd"),
        juz: pick("juz"),
        ruku: pick("ruku"),
        masala: pick("masala"),
        jobId: latestJob?.id ?? null,
        engine: p.engine,
        checksum: p.checksum,
        language: p.language,
        textState: p.verifiedText ? "verified" : p.normalizedText ? "raw+normalized" : "raw",
        verified: p.verified,
        ocrConfidence: p.ocrConfidence,
        signals,
      };
      return {
        entityType: "BOOK_PAGE",
        entityId: p.id,
        title: `${book.titleEn} — vol. ${p.volume}, p. ${p.pageNumber}`,
        body: display,
        bodySearch: normalizeSearchText(display).slice(0, 8000),
        language: pageLanguage(p.language, display),
        route: `#/sources/book/${book.slug}`,
        weight: 1,
        bookId: book.id,
        // Phase 5: queryable jild/page filter keys (meta stays the record).
        volume: p.volume,
        pageNumber: p.pageNumber,
        meta: JSON.stringify(meta).slice(0, 4000),
      };
    });
    if (docs.length > 0) {
      // SQLite bulk insert in chunks (variable-limit safe).
      for (let i = 0; i < docs.length; i += 100) {
        await db.searchDocument.createMany({ data: docs.slice(i, i + 100) });
      }
      await db.bookPage.updateMany({
        where: { bookId: book.id, status: "OCR_DONE" },
        data: { status: "INDEXED" },
      });
    }
    return NextResponse.json({
      book: { id: book.id, slug: book.slug, titleEn: book.titleEn },
      pagesConsidered: pages.length,
      docs: docs.length,
    });
  } catch {
    return NextResponse.json({ error: "Reindex failed." }, { status: 500 });
  }
}
