import { NextRequest, NextResponse } from "next/server";
import { db } from "@/lib/db";

/**
 * Public book pages for the source viewer (Phase 7).
 * GET ?slug= &volume? &take?(&le;50) &skip= → { pages, total, volumes }.
 * Text included (viewer needs it); paginated so browsers never load a book.
 * Admin mutations stay on /api/admin/pages (keyed).
 */
export async function GET(req: NextRequest) {
  const sp = req.nextUrl.searchParams;
  const slug = (sp.get("slug") ?? "").trim();
  if (!slug) return NextResponse.json({ error: "slug is required" }, { status: 400 });
  const volumeRaw = sp.get("volume");
  const take = Math.min(Math.max(parseInt(sp.get("take") ?? "20", 10) || 20, 1), 50);
  const skip = Math.max(parseInt(sp.get("skip") ?? "0", 10) || 0, 0);
  try {
    const book = await db.book.findUnique({ where: { slug }, select: { id: true } });
    if (!book) return NextResponse.json({ error: "Book not found" }, { status: 404 });
    const where: Record<string, unknown> = { bookId: book.id };
    if (volumeRaw !== null && volumeRaw !== "") {
      const volume = Number(volumeRaw);
      if (!Number.isInteger(volume) || volume < 1) {
        return NextResponse.json({ error: "volume must be a positive integer" }, { status: 400 });
      }
      where.volume = volume;
    }
    const [pages, total, volumes] = await Promise.all([
      db.bookPage.findMany({
        where,
        orderBy: [{ volume: "asc" }, { pageNumber: "asc" }],
        take,
        skip,
        select: {
          id: true, volume: true, pageNumber: true, chapter: true, status: true,
          language: true, engine: true, ocrConfidence: true, verified: true,
          imageUrl: true, ocrText: true, normalizedText: true, verifiedText: true,
          ocrTextSecondary: true, engineSecondary: true, ocrConfidenceSecondary: true,
          updatedAt: true,
        },
      }),
      db.bookPage.count({ where }),
      db.bookPage.findMany({ where: { bookId: book.id }, select: { volume: true }, distinct: ["volume"], orderBy: { volume: "asc" } }),
    ]);
    return NextResponse.json({ pages, total, volumes: volumes.map((v) => v.volume) });
  } catch {
    return NextResponse.json({ error: "Failed to load pages." }, { status: 500 });
  }
}
