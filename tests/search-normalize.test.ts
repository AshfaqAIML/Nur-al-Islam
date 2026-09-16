/** Phase 4 tests — search normalization (display vs index separation). */
import { describe, expect, test } from "bun:test";
import { guessLanguage, normalizeSearchText } from "../src/lib/search-normalize";

describe("normalizeSearchText", () => {
  test("strips tashkeel + kashida, folds alef, keeps teh-marbuta", () => {
    expect(normalizeSearchText("بِسْمِ اللَّهِ")).toBe("بسم الله");
    expect(normalizeSearchText("كـتـاب")).toBe("كتاب");
    expect(normalizeSearchText("أحمد إسلام قرآن")).toBe("احمد اسلام قران");
    expect(normalizeSearchText("مدرسة")).toBe("مدرسة"); // ة untouched
    expect(normalizeSearchText("  a   b \n\n\n c ").replace(/\n/g, "|")).toBe("a b || c");
  });

  test("stripTashkeel=false preserves diacritics (Quranic text)", () => {
    const raw = "بِسْمِ اللَّهِ";
    expect(normalizeSearchText(raw, false)).toContain("ِ");
    expect(normalizeSearchText(raw, false)).not.toContain("ـ");
  });

  test("latin text passes through structurally", () => {
    expect(normalizeSearchText("washing the FACE")).toBe("washing the FACE");
  });

  test("Urdu codepoint folding (verified EasyOCR behavior)", () => {
    const urduYeh = "تبیا"; // T-B-06CC-A
    const arabYeh = "تبيا"; // T-B-064A-A
    expect(urduYeh).not.toBe(arabYeh);
    expect(normalizeSearchText(urduYeh)).toBe(normalizeSearchText(arabYeh));
  });
});

describe("guessLanguage", () => {
  test("ur / ar / en / defaults", () => {
    expect(guessLanguage("یہ آزمائشی ہے")).toBe("UR");
    expect(guessLanguage("كتاب الطهارة")).toBe("AR");
    expect(guessLanguage("washing the face")).toBe("EN");
    expect(guessLanguage("باب الوضوء washing")).toBe("AR"); // script-dominant
    expect(guessLanguage("123 !?")).toBe("EN"); // column-default fallback
    expect(guessLanguage("")).toBe("EN");
  });
});
