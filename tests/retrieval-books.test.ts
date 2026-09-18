/**
 * Phase 5 tests — retrieval against a scratch SQLite DB.
 *
 * Proves, with the REAL retrieveEvidence() + Prisma stack:
 * - pre-existing families (misconception/quran/book) still retrieve with
 *   identical scores and intact enrichment (non-breaking integration);
 * - BOOK_PAGE docs participate as a new source family with
 *   volume/page provenance in the AI context body;
 * - Urdu-variant queries match via bodySearch while old rows score
 *   byte-identically (bodySearch NULL → zero bonus).
 *
 * Setup: schema must be pushed once to the scratch DB —
 *   DATABASE_URL="file:<tmp>/phase5-test.db" bunx prisma db push
 * The suite seeds and removes its own rows (prefix "p5").
 */
import { afterAll, beforeAll, describe, expect, test } from "bun:test";

process.env.DATABASE_URL = "file:C:/Users/moham/AppData/Local/Temp/opencode/phase5-test.db";

const { retrieveEvidence } = await import("../src/lib/retrieval");
const { PrismaClient } = await import("@prisma/client");

const db = new PrismaClient();
const IDS = { misc: "", quran: "", book: "", scholar: "", page: "", fzBook: "" };

async function cleanup() {
  // NOTE: BOOK/BOOK_PAGE docs carry cuid entityIds (page/book row IDs), so
  // entityId-prefix cleanup alone leaks them across runs — stale rows then
  // crowd the top-12 retrieval window. Clean by title prefix too.
  await db.searchDocument.deleteMany({
    where: { OR: [{ entityId: { startsWith: "p5" } }, { title: { startsWith: "P5 " } }] },
  });
  await db.bookPage.deleteMany({ where: { book: { slug: "p5-fatawa" } } });
  await db.book.deleteMany({ where: { slug: "p5-fatawa" } });
  await db.scholar.deleteMany({ where: { slug: "p5-scholar" } });
}

beforeAll(async () => {
  await cleanup();
  const scholar = await db.scholar.create({
    data: { slug: "p5-scholar", nameEn: "P5 Scholar", classification: "CLASSICAL_HANAFI" },
  });
  const book = await db.book.create({
    data: { slug: "p5-fatawa", titleEn: "P5 Fatawa", language: "Urdu", volumes: 12, authorId: scholar.id },
  });
  const page = await db.bookPage.create({
    data: { bookId: book.id, volume: 4, pageNumber: 112, chapter: "P5 Chapter", ocrText: "P5 raw ocr text", status: "OCR_DONE", language: "ur", engine: "easyocr/v1" },
  });
  await db.searchDocument.createMany({
    data: [
      { entityType: "MISCONCEPTION", entityId: "p5m1", title: "P5 Tawassul ruling", body: "P5 tawassul body text here", route: "misconceptions/p5", weight: 1.4 },
      { entityType: "QURAN", entityId: "p5q1", title: "P5 Remembrance verse", body: "P5 remembrance body", route: "quran-hadith/quran/p5q1", weight: 1 },
      { entityType: "BOOK", entityId: book.id, title: "P5 Fatawa", body: "P5 collected fatwas", route: "sources/book/p5-fatawa", weight: 1 },
      {
        entityType: "BOOK_PAGE", entityId: page.id, title: "P5 Fatawa — vol. 4, p. 112",
        body: "P5 raw ocr text", bodySearch: "P5 raw ocr text", language: "UR",
        route: "#/sources/book/p5-fatawa", weight: 1, bookId: book.id, volume: 4, pageNumber: 112,
      },
      {
        entityType: "BOOK_PAGE", entityId: "p5fold", title: "P5 fold probe",
        body: "X", bodySearch: "A\u064AB", language: "UR", // A + U+064A + B
        route: "#/sources/book/p5-fatawa", weight: 1, bookId: book.id,
      },
    ],
  });
  IDS.misc = "p5m1"; IDS.quran = "p5q1"; IDS.book = book.id; IDS.scholar = scholar.id; IDS.page = page.id; IDS.fzBook = book.id;
});

afterAll(async () => {
  await cleanup();
  await db.$disconnect();
});

describe("existing families unbroken", () => {
  test("misconception retrieves with legacy score + CLAIM enrichment", async () => {
    const hits = await retrieveEvidence("p5 tawassul");
    // terms: ["p5","tawassul"]; m1: title has both (+3+3), hay has both (+1+1) = 8 × 1.4 = 11.2
    const m = hits.find((h) => h.entityId === "p5m1")!;
    expect(m.score).toBeCloseTo(11.2, 6);
    expect(hits[0].entityId).toBe("p5m1");
  });

  test("quran doc scores exactly (title 3 + hay 1, weight 1)", async () => {
    const hits = await retrieveEvidence("p5 remembrance");
    const q = hits.find((h) => h.entityId === "p5q1")!;
    // "p5": title+3, hay+1; "remembrance": title+3, hay+1 → 8 × 1 = 8
    expect(q.score).toBe(8);
  });

  test("book catalog enrichment intact", async () => {
    // "p5 fatawa" hits the BOOK doc title twice (p5, fatawa): (3+1)*2=8
    const hits = await retrieveEvidence("p5 fatawa");
    const b = hits.find((h) => h.entityId === IDS.book)!;
    expect(b.body.startsWith("BOOK [")).toBe(true);
    expect(b.body).toContain("P5 Fatawa");
  });
});

describe("books as an additional source family", () => {
  test("BOOK_PAGE participates with volume/page provenance in context body", async () => {
    const hits = await retrieveEvidence("p5 raw ocr");
    const p = hits.find((h) => h.entityId === IDS.page)!;
    expect(p.entityType).toBe("BOOK_PAGE");
    expect(p.body).toContain("BOOK EXCERPT");
    expect(p.body).toContain("P5 Fatawa");
    expect(p.body).toContain("vol. 4, p. 112");
    expect(p.body).toContain("P5 Chapter");
    expect(p.body).toContain("OCR, unverified");
  });

  test("Urdu-variant query matches via bodySearch (fold backstop)", async () => {
    const hits = await retrieveEvidence("A\u06CCB"); // A + U+06CC + B
    const f = hits.find((h) => h.entityId === "p5fold")!;
    // folded term hits bodySearch only: +1 × weight 1
    expect(f.score).toBe(1);
  });

  test("old rows score identically with book docs present", async () => {
    const hits = await retrieveEvidence("p5 remembrance");
    // corpus-wide: q1 still exactly 8 — book rows add no phantom score
    expect(hits.find((h) => h.entityId === "p5q1")!.score).toBe(8);
  });
});
