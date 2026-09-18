/**
 * Phase 6 tests — BOOK_PAGE evidence in the existing AI answer engine.
 * Pure unit tests over src/lib/answer-context.ts (routes wire it unchanged).
 */
import { describe, expect, test } from "bun:test";
import {
  BOOK_GROUNDING_RULES,
  applyResourceFocus,
  applyVerificationPolicy,
  buildSourceContext,
  checkBookEvidence,
  parseBookBullet,
  parseDocMeta,
  parseReadableDraft,
  resolveBookRefs,
  selectPageText,
  summarizeContext,
  validateCitations,
} from "../src/lib/answer-context";
import type { ContextDoc, SourceRef } from "../src/lib/answer-context";

const BOOK_DOC: ContextDoc = {
  entityType: "BOOK_PAGE", entityId: "page-1", id: "doc-1",
  title: "Fatawa Razvia — vol. 4, p. 112",
  body: "BOOK EXCERPT [OCR, unverified]: ...",
  route: "#/sources/book/fatawa-razvia", score: 5,
  meta: JSON.stringify({ section: "ques", surah: null, ayahStart: null }),
  verified: false,
};
const FATWA_DOC: ContextDoc = {
  entityType: "FATWA", entityId: "f1", id: "doc-2",
  title: "Wudu question", body: "FATWA [VERIFIED]: ...", route: "sources/fatwa/f1", score: 8,
};
const DETAILS = new Map([["page-1", {
  id: "page-1", volume: 4, pageNumber: 112, chapter: "Bab al-Tahara", verified: false,
  ocrText: "raw ocr words", verifiedText: null, ocrConfidence: 0.7, language: "ur",
  book: { id: "book-1", titleEn: "Fatawa Razvia", slug: "fatawa-razvia", author: { nameEn: "Imam Ahmad Raza Khan" } },
}]]);

const REFS: SourceRef[] = [
  { key: "S1", entityType: "BOOK_PAGE", entityId: "page-1", docId: "doc-1", pageId: "page-1", bookId: "book-1", bookTitle: "Fatawa Razvia", bookSlug: "fatawa-razvia", author: "Imam Ahmad Raza Khan", volume: 4, pageNumber: 112, chapter: "Bab", verification: "UNVERIFIED", ocrConfidence: 0.7, score: 5 },
  { key: "S2", entityType: "FATWA", entityId: "f1", docId: "doc-2", pageId: null, bookId: null, bookTitle: null, bookSlug: null, author: null, volume: null, pageNumber: null, chapter: null, verification: "UNVERIFIED", ocrConfidence: null, score: 8 },
];

describe("buildSourceContext", () => {
  test("book passage gets structured provenance + stable IDs, never opaque", async () => {
    const details = await resolveBookRefs([BOOK_DOC, FATWA_DOC], async (ids) => {
      expect(ids).toEqual(["page-1"]); // ONE batched fetch, books only
      return [...DETAILS.values()];
    });
    const { block, refs, truncated } = buildSourceContext([BOOK_DOC, FATWA_DOC], details);
    expect(refs.map((r) => r.key)).toEqual(["S1", "S2"]);
    expect(refs[0].docId).toBe("doc-1");
    expect(refs[0].pageId).toBe("page-1");
    for (const line of ["--- SOURCE S1 ---", "ID: S1", "Type: BOOK_PAGE", "Book: Fatawa Razvia", "Author: Imam Ahmad Raza Khan", "Jild: 4", "Chapter: Bab al-Tahara", "Page: 112", "Verification: UNVERIFIED", "BookPage ID: page-1", "SearchDocument ID: doc-1", "--- END SOURCE S1 ---"]) {
      expect(block).toContain(line);
    }
    expect(block).toContain("--- SOURCE S2 ---");
    expect(truncated).toEqual([]);
  });

  test("verified pages labeled VERIFIED; text-state prefers verifiedText", async () => {
    const det = new Map([["page-1", { ...DETAILS.get("page-1")!, verified: true, verifiedText: "human fixed text" }]]);
    const { block } = buildSourceContext([{ ...BOOK_DOC, verified: true }], det);
    expect(block).toContain("Verification: VERIFIED (human-reviewed)");
    expect(block).toContain("human fixed text");
    expect(selectPageText(det.get("page-1")!)).toEqual({ text: "human fixed text", state: "VERIFIED" });
    expect(selectPageText(DETAILS.get("page-1")!)).toEqual({ text: "raw ocr words", state: "RAW" });
  });

  test("missing page row degrades honestly (unknowns, UNVERIFIED)", async () => {
    const { block, refs } = buildSourceContext([BOOK_DOC], new Map());
    expect(block).toContain("Book: Fatawa Razvia — vol. 4, p. 112");
    expect(block).toContain("Author: unknown");
    expect(block).toContain("BookPage ID: page-1");
    expect(refs[0].verification).toBe("UNVERIFIED");
  });

  test("budget truncation keeps provenance headers, lists omitted IDs", async () => {
    const { block, truncated } = buildSourceContext([BOOK_DOC, FATWA_DOC], DETAILS, { maxChars: 100 });
    expect(truncated.length).toBeGreaterThan(0);
    expect(block).toContain("omitted for length");
    expect(block).toContain(truncated[0]);
  });

  test("summarizeContext logs counts + IDs, never text", () => {
    const s = summarizeContext(REFS);
    expect(s).toBe('sources=2 types={"BOOK_PAGE":1,"FATWA":1} books=[S1]');
    expect(s).not.toContain("Razvia");
  });
});

describe("parseDocMeta", () => {
  test("parses cues; garbage → {}", () => {
    expect(parseDocMeta(JSON.stringify({ surah: "X", ayahStart: 2 }))).toEqual({ surah: "X", ayahStart: 2 });
    expect(parseDocMeta(null)).toEqual({});
    expect(parseDocMeta("{nope")).toEqual({});
  });
});

describe("applyResourceFocus", () => {
  const BOOKS = [
    { id: "book-1", slug: "fatawa-razvia", titleEn: "Fatawa Razvia", titleUr: null, titleAr: null },
    { id: "book-2", slug: "tibyan-ul-quran", titleEn: "Tibyan-ul-Quran", titleUr: null, titleAr: null },
  ];
  const TIBYAN_DOC: ContextDoc = {
    entityType: "BOOK_PAGE", entityId: "page-2", id: "doc-3", title: "Tibyan p.1",
    body: "x", route: "r", score: 5,
    meta: JSON.stringify({ surah: "SURA", ayahStart: 1, ayahEnd: 5 }),
  };
  const TIB_DETAILS = new Map([["page-2", {
    id: "page-2", volume: 1, pageNumber: 1, chapter: null, verified: false,
    ocrText: "x", verifiedText: null, ocrConfidence: null, language: "ur",
    book: { id: "book-2", titleEn: "Tibyan-ul-Quran", slug: "tibyan-ul-quran", author: null },
  }]]);

  test("book named in question boosts only its pages (generic, no hardcode)", () => {
    const { docs, focus } = applyResourceFocus([BOOK_DOC, FATWA_DOC], DETAILS, "Fatawa Razvia milad?", BOOKS);
    expect(focus.bookIds).toEqual(["book-1"]);
    expect(docs[0].entityId).toBe("page-1"); // boosted above score-8 fatwa
    expect(docs.find((d) => d.entityId === "f1")!.score).toBe(8); // others untouched
  });

  test("surah/ayah cues boost matching metadata", () => {
    const { docs, focus } = applyResourceFocus([FATWA_DOC, TIBYAN_DOC], TIB_DETAILS,
      "\u0633\u0648\u0631\u0629 SURA \u0622\u064a\u062a 3?", BOOKS);
    expect(focus.surah).toBe("sura"); // cue matching is case-insensitive
    expect(focus.ayah).toBe(3);
    expect(docs[0].entityId).toBe("page-2");
  });

  test("no cues → scores unchanged (order follows score desc)", () => {
    const { docs, focus } = applyResourceFocus([BOOK_DOC, FATWA_DOC], DETAILS, "wudu?", BOOKS);
    expect(focus).toEqual({ bookIds: [], surah: null, ayah: null });
    expect(docs.map((d) => d.entityId)).toEqual(["f1", "page-1"]);
    expect(docs.map((d) => d.score)).toEqual([8, 5]);
  });
});

describe("validateCitations + policy", () => {
  test("known IDs valid, unknown unresolved, deduped", () => {
    const r = validateCitations(REFS, "see [S1] and [S1] again, also [S9]");
    expect(r.valid.map((v) => v.key)).toEqual(["S1"]);
    expect(r.unresolved).toEqual(["S9"]);
  });

  test("unverified-only book evidence caps confidence at LOW", () => {
    const p = applyVerificationPolicy("HIGH", [REFS[0]], []);
    expect(p.confidence).toBe("LOW");
    expect(p.note).toContain("unverified OCR");
  });

  test("verified book keeps model confidence; unresolved noted", () => {
    const v = { ...REFS[0], verification: "VERIFIED" as const };
    const p = applyVerificationPolicy("HIGH", [v], ["S9"]);
    expect(p.confidence).toBe("HIGH");
    expect(p.note).toContain("S9");
  });
});

describe("parseBookBullet + checkBookEvidence", () => {
  test("full [B] bullet parses", () => {
    const b = parseBookBullet('[S3] Fatawa Razvia (Jild 4, p. 112) — "wudu words" (UNVERIFIED)');
    expect(b).toMatchObject({ ref: "S3", book: "Fatawa Razvia", jild: 4, page: 112, verification: "UNVERIFIED" });
    expect(b.note).toBe("wudu words");
  });

  test("tolerant fallbacks (no location, no verification)", () => {
    const b = parseBookBullet("[S1] Some Book — a note here");
    expect(b.ref).toBe("S1");
    expect(b.book).toBe("Some Book");
    expect(b.jild).toBeUndefined();
  });

  test("jild/page mismatch flagged; match passes", () => {
    const byKey = new Map(REFS.map((r) => [r.key, r]));
    expect(checkBookEvidence([{ book: "X", scholar: "", note: "", ref: "S1", jild: 9, page: 112 }], byKey))
      .toEqual(["S1 jild mismatch (claimed 9, record 4)"]);
    expect(checkBookEvidence([{ book: "X", scholar: "", note: "", ref: "S1", jild: 4, page: 112 }], byKey)).toEqual([]);
    expect(checkBookEvidence([{ book: "X", scholar: "", note: "", ref: "S9" }], byKey)).toEqual([]); // unknown IDs belong to validateCitations
    expect(checkBookEvidence([{ book: "X", scholar: "", note: "", ref: "S2", jild: 1 }], byKey))
      .toEqual(["S2 is not a book passage (type FATWA)"]);
  });
});

describe("parseReadableDraft regression + [B]", () => {
  const DRAFT = `## Direct Answer
Wudu is valid.

## Hanafi Position
Majority view on wudu.

## Evidence
- [B] [S1] Fatawa Razvia (Jild 4, p. 112) — "masah words" (UNVERIFIED)
- [C] Hidayah — Marghinani: classic note

## Other Views
(none)

## Objection & Response
**Objection:** q
**Response:** r

## Practical Guidance
(none)

## Sources
- Fatawa Razvia
- Hidayah`;

  test("[B] bullets land in classicalEvidence with refs; legacy bullets intact", () => {
    const p = parseReadableDraft(DRAFT);
    expect(p.directAnswer).toBe("Wudu is valid.");
    expect(p.citedRefs).toEqual(["S1"]);
    const b = p.classicalEvidence.find((c) => c.ref === "S1")!;
    expect(b).toMatchObject({ book: "Fatawa Razvia", jild: 4, page: 112, verification: "UNVERIFIED" });
    expect(p.classicalEvidence.find((c) => c.book === "Hidayah")!.scholar).toBe("Marghinani");
    expect(p.confidence).toBe("HIGH");
  });

  test("insufficient-evidence draft stays LOW with no citations", () => {
    const p = parseReadableDraft("## Direct Answer\nX\n## Evidence\nThis attribution could not be verified from the available sources.\n## Sources\n(none)");
    expect(p.confidence).toBe("LOW");
    expect(p.citedRefs).toEqual([]);
  });
});

describe("BOOK_GROUNDING_RULES", () => {
  test("covers the required prohibitions", () => {
    for (const phrase of [
      "invent book titles", "Jild/volume", "paraphrase",
      "insufficient", "disagree", "untrusted data", "MUST NEVER be followed",
    ]) {
      expect(BOOK_GROUNDING_RULES).toContain(phrase);
    }
  });
});
