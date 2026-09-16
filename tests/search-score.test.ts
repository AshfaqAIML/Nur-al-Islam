/**
 * Phase 5 tests — shared scorer. Backward-compatibility contract:
 * documents WITHOUT bodySearch score EXACTLY as the pre-Phase-5 route.
 * (Scores below were hand-computed from the legacy algorithm.)
 */
import { describe, expect, test } from "bun:test";
import { attachProvenance, extractPhrases, scoreDocuments, tokenizeTerms } from "../src/lib/search-score";
import type { SearchDocInput } from "../src/lib/search-score";

const OLD_MISCONCEPTION: SearchDocInput = {
  entityType: "MISCONCEPTION", entityId: "m1",
  title: "Tawassul through the Prophet",
  body: "Tawassul means seeking a means to Allah. The Hanafi position permits tawassul through the Prophet.",
  route: "misconceptions/tawassul", weight: 1.4,
};
const OLD_QURAN: SearchDocInput = {
  entityType: "QURAN", entityId: "q1",
  title: "Al-Baqarah 2:152",
  body: "So remember Me and I will remember you. Arabic text of remembrance.",
  route: "quran-hadith/quran/q1", weight: 1,
};
const OLD_BOOK: SearchDocInput = {
  entityType: "BOOK", entityId: "b1",
  title: "Fatawa Razvia",
  body: "Collected fatwas of Ahmad Raza Khan on Hanafi fiqh.",
  route: "sources/book/fatawa-razvia", weight: 1,
};
// New Phase-4 style page doc: verbatim Arabic-form body + folded index.
const FATAWA_PAGE: SearchDocInput = {
  entityType: "BOOK_PAGE", entityId: "p1",
  title: "Fatawa Razvia — vol. 4, p. 112",
  body: "مسئلہ نمبر 112 سوال وضو جواب مسح",
  bodySearch: "مسئلہ نمبر 112 سوال وضو جواب مسح",
  language: "UR", route: "#/sources/book/fatawa-razvia",
  weight: 1, bookId: "book-fatawa", volume: 4, pageNumber: 112,
};
const TIBYAN_PAGE: SearchDocInput = {
  entityType: "BOOK_PAGE", entityId: "p2",
  title: "Tibyan-ul-Quran — vol. 1, p. 7",
  body: "سورۃ البقرۃ آیت 2 تفسیر",
  bodySearch: "سورۃ البقرۃ آیت 2 تفسیر",
  language: "AR", route: "#/sources/book/tibyan",
  weight: 1, bookId: "book-tibyan", volume: 1, pageNumber: 7,
};
const CORPUS = [OLD_MISCONCEPTION, OLD_QURAN, OLD_BOOK, FATAWA_PAGE, TIBYAN_PAGE];

describe("legacy ranking preserved", () => {
  test("tawassul scores exactly as the old route", () => {
    const hits = scoreDocuments(CORPUS, "tawassul");
    const m = hits.find((h) => h.entityId === "m1")!;
    // elif chain: title hit (+4), body not additionally counted = 4
    expect(m.score).toBe(4);
    expect(hits[0].entityId).toBe("m1");
    expect(m.snippet).toBe(OLD_MISCONCEPTION.body.slice(0, 220));
  });

  test("single body term scores +2, typo floor 1.5", () => {
    const hits = scoreDocuments(CORPUS, "remembrance");
    expect(hits.find((h) => h.entityId === "q1")!.score).toBe(2);
    // "remembrancex" matches nothing literally; prefix "remembrance" hits → 1.5
    const typo = scoreDocuments(CORPUS, "remembrancex");
    expect(typo.find((h) => h.entityId === "q1")!.score).toBe(1.5);
  });

  test("no match → no hits; empty-ish query → none", () => {
    expect(scoreDocuments(CORPUS, "xyzzyplugh")).toEqual([]);
    expect(scoreDocuments(CORPUS, "a")).toEqual([]);
  });
});

describe("normalized (folded) matching", () => {
  test("Urdu-variant query matches folded bodySearch (milad example)", () => {
    const doc: SearchDocInput = {
      entityType: "BOOK_PAGE", entityId: "p9",
      title: "Fatawa Razvia — vol. 9, p. 3",
      body: "میلاد النبی", // Arabic-form Beh spelling as OCR emits
      bodySearch: "میلاد النبی",
      route: "#/sources/book/f", weight: 1, bookId: "b", volume: 9,
    };
    // Query typed with Urdu-specific forms folds to the same index terms.
    const hits = scoreDocuments([doc], "میلاد النبی");
    expect(hits.length).toBe(1);
    expect(hits[0].score).toBeGreaterThan(0);
  });

  test("folded variant matches only via bodySearch (escape-pinned)", () => {
    // Doc indexed with Arabic yeh (U+064A, as OCR emits); query uses
    // Urdu yeh (U+06CC). Raw comparison fails; folded comparison hits +2.
    const doc: SearchDocInput = {
      entityType: "BOOK_PAGE", entityId: "pv",
      title: "X",
      body: "X",
      bodySearch: "A\u064AB", // A + U+064A + B (OCR-emitted form)
      route: "r", weight: 1, bookId: "b",
    };
    const hits = scoreDocuments([doc], "A\u06CCB"); // A + U+06CC + B (Urdu-typed query)
    expect(hits.length).toBe(1);
    expect(hits[0].score).toBe(2);
  });

  test("bodySearch is a backstop, never a double-count", () => {
    // Term present in BOTH body and bodySearch scores once (elif chain).
    const hits = scoreDocuments([FATAWA_PAGE], "سوال");
    expect(hits[0].score).toBe(2);
  });
});

describe("phrase search", () => {
  test("quoted phrase filters + boosts", () => {
    const hits = scoreDocuments(CORPUS, '"Hanafi position"');
    expect(hits.length).toBe(1);
    expect(hits[0].entityId).toBe("m1");
    expect(hits[0].score).toBeGreaterThanOrEqual(6);
    expect(hits[0].snippet).toContain("Hanafi position");
  });

  test("absent phrase eliminates", () => {
    expect(scoreDocuments(CORPUS, '"no such phrase anywhere"')).toEqual([]);
  });

  test("extractPhrases splits quotes from terms", () => {
    expect(extractPhrases('"a b" c d')).toEqual({ phrases: ["a b"], rest: "  c d" });
    expect(extractPhrases("plain")).toEqual({ phrases: [], rest: "plain" });
    expect(tokenizeTerms("  a bb ccc ")).toEqual(["bb", "ccc"]);
  });
});

describe("metadata filtering", () => {
  test("type restricts all families", () => {
    const hits = scoreDocuments(CORPUS, "razvia", { type: "BOOK_PAGE" });
    expect(hits.every((h) => h.entityType === "BOOK_PAGE")).toBe(true);
  });

  test("bookId scopes only BOOK_PAGE docs", () => {
    const hits = scoreDocuments(CORPUS, "razvia", { bookId: "book-fatawa" });
    // BOOK catalog row (no bookId) still passes; other book's page is out.
    expect(hits.some((h) => h.entityId === "b1")).toBe(true);
    expect(hits.some((h) => h.entityId === "p2")).toBe(false);
    expect(hits.some((h) => h.entityId === "p1")).toBe(true);
  });

  test("volume scopes only BOOK_PAGE docs (jild filtering)", () => {
    const hits = scoreDocuments([FATAWA_PAGE, TIBYAN_PAGE], "vol", { volume: 4 });
    expect(hits.map((h) => h.entityId)).toEqual(["p1"]);
    // Other families pass through volume filters untouched.
    const mixed = scoreDocuments(CORPUS, "tawassul", { volume: 4 });
    expect(mixed.some((h) => h.entityId === "m1")).toBe(true);
  });

  test("combined type + bookId + volume", () => {
    const hits = scoreDocuments(CORPUS, "سوال", { type: "BOOK_PAGE", bookId: "book-fatawa", volume: 4 });
    expect(hits.map((h) => h.entityId)).toEqual(["p1"]);
  });
});

describe("attachProvenance", () => {
  test("BOOK_PAGE hits gain full provenance; others get null", async () => {
    const hits = scoreDocuments(CORPUS, "razvia"); // BOOK catalog row + page
    expect(hits.map((h) => h.entityId).sort()).toEqual(["b1", "p1"]);
    const withProv = await attachProvenance(hits, async (ids) => {
      expect(ids).toEqual(["p1"]);
      return new Map(ids.map((id) => [id, {
        id, volume: 4, pageNumber: 112, chapter: "باب الطہارۃ", verified: false,
        book: { id: "book-fatawa", titleEn: "Fatawa Razvia", slug: "fatawa-razvia", author: { nameEn: "Ahmad Raza Khan" } },
      }]));
    });
    const page = withProv.find((h) => h.entityId === "p1")!;
    expect(page.provenance).toMatchObject({
      bookTitle: "Fatawa Razvia", author: "Ahmad Raza Khan",
      volume: 4, page: 112, pageId: "p1", verified: false,
    });
    expect(withProv.find((h) => h.entityId === "b1")!.provenance).toBeNull();
  });

  test("missing page row → null provenance (never throws)", async () => {
    const hits = scoreDocuments([FATAWA_PAGE], "سوال");
    const withProv = await attachProvenance(hits, async () => new Map());
    expect(withProv[0].provenance).toBeNull();
  });
});
