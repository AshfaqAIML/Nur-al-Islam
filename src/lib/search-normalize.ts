/**
 * Search normalization for Urdu/Arabic (Phase 4).
 *
 * Produces the index-time `bodySearch` variant stored on SearchDocument.
 * Display text (`body`) is ALWAYS the verbatim source — this module only
 * feeds the search field. Rules are intentionally conservative and scoped:
 * NFC + kashida removal + alef folding (أإآٱ→ا) + tashkeel strip.
 * Teh-marbuta/heh are NEVER folded (meaning-bearing). One documented
 * exception: Urdu-specific codepoints U+06CC/U+06C3 fold to their Arabic
 * forms U+064A/U+0629, because vision OCR models trained on Arabic script
 * emit Arabic forms even for Urdu input (verified vs EasyOCR 1.7.2) — both
 * sides of the search comparison fold identically, so Urdu queries match
 * regardless of input spelling. Display text (`body`) is never folded.
 * Mirrors mini-services/ocr-worker/normalize.py.
 */
export function normalizeSearchText(text: string, stripTashkeel = true, foldAlef = true): string {
  let out = text.normalize("NFC");
  out = out.replace(/ـ/g, ""); // kashida / tahdeed U+0640
  // foldAlef=false preserves U+0622/U+0623/U+0625 for cue detection patterns
  // that use standard forms (mirrors worker fold_variants).
  if (foldAlef) out = out.replace(/[أإآٱ]/g, "ا"); // alef variants → bare alef
  out = out.replace(/\u06CC/g, "\u064A").replace(/\u06C3/g, "\u0629").replace(/\u0649/g, "\u064A"); // U+06CC/U+0649->U+064A, U+06C3->U+0629 (search only)
  if (stripTashkeel) {
    out = out.replace(/[ً-ٲً-ٰٖ]/g, ""); // tashkeel U+064B–U+0652 + U+0670
  }
  out = out.replace(/[ \t]+/g, " ");
  out = out.replace(/\n{3,}/g, "\n\n");
  return out.trim();
}

/**
 * Language guess for index `language` (AR | UR | EN), aligned with the
 * worker's detect_language and the RAG detector. Script-dominant:
 * Urdu-specific codepoints → UR, Arabic+Latin mix without Urdu → AR,
 * Latin-only → EN, empty/unknown → EN (matches the column's "EN" default).
 */
export function guessLanguage(text: string): "AR" | "UR" | "EN" {
  const arabic = (text.match(/[؀-ۿ]/g) || []).length;
  if (arabic === 0) return "EN";
  // Urdu-specific codepoints as explicit escapes (homoglyph-safe: ب U+0628
  // must never mix with ں U+06BA). Same set as retrieval.ts + worker normalize.py.
  const urdu = (text.match(/[\u0679\u0688\u0691\u06BA\u06BE\u06C1\u06C3\u06D2\u06AF\u0686\u0698]/g) || []).length;
  if (urdu > 0) return "UR";
  return arabic > 2 ? "AR" : "EN";
}
