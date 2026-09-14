/** Phase 7 tests — book frontend contracts (pure helpers only). */
import { describe, expect, test } from "bun:test";
import {
  buildBookPageParam, formatJild, isTerminalJob, JOB_STATUS_META,
  jobProgress, PAGE_STATUS_META, parseSourcesParam,
  pageReviewedFrom, pageReviewReasons,
} from "../src/lib/book-api";

describe("deep-link contract (hash router compatible)", () => {
  test("buildBookPageParam produces book/{slug}/{page}", () => {
    expect(buildBookPageParam("fatawa-razvia", 112)).toBe("book/fatawa-razvia/112");
  });

  test("parseSourcesParam round-trips book pages, tolerates bad input", () => {
    expect(parseSourcesParam("book/fatawa-razvia/112")).toEqual({ kind: "book", slug: "fatawa-razvia", page: 112 });
    expect(parseSourcesParam("book/fatawa-razvia")).toEqual({ kind: "book", slug: "fatawa-razvia", page: null });
    expect(parseSourcesParam("scholar/ibn-abidin")).toEqual({ kind: "scholar", slug: "ibn-abidin", page: null });
    expect(parseSourcesParam(null)).toBeNull();
    expect(parseSourcesParam("")).toBeNull();
    expect(parseSourcesParam("book")).toBeNull();
    expect(parseSourcesParam("book/slug/0")).toEqual({ kind: "book", slug: "slug", page: null });
    expect(parseSourcesParam("book/slug/abc")).toEqual({ kind: "book", slug: "slug", page: null });
    expect(parseSourcesParam("nope/x")).toBeNull();
    // Round-trip: built param parses back identically.
    const built = buildBookPageParam("tibyan", 7);
    expect(parseSourcesParam(built)).toEqual({ kind: "book", slug: "tibyan", page: 7 });
  });
});

describe("jild formatting (no manual reversal; bidi handled by dir=auto)", () => {
  test("en/ur/ar", () => {
    expect(formatJild(4, "en")).toBe("Vol. 4");
    expect(formatJild(4, "ur")).toBe("جلد 4");
    expect(formatJild(4, "ar")).toBe("المجلد 4");
    expect(formatJild(null, "en")).toBe("");
  });
});

describe("job state helpers (mirror backend vocabulary)", () => {
  test("terminal detection", () => {
    for (const s of ["COMPLETED", "COMPLETED_WITH_WARNINGS", "FAILED", "CANCELLED"]) {
      expect(isTerminalJob(s)).toBe(true);
    }
    for (const s of ["QUEUED", "OCR", "VERIFYING", "REQUIRES_REVIEW", "INDEXING"]) {
      expect(isTerminalJob(s)).toBe(false);
    }
  });

  test("progress prefers counters, guards divide-by-zero", () => {
    expect(jobProgress({ progress: 0, totalPages: 0, processedPages: 0 })).toBe(0);
    expect(jobProgress({ progress: 0.5, totalPages: 8, processedPages: 2 })).toBe(25);
    expect(jobProgress({ progress: 0.9, totalPages: 0, processedPages: 0 })).toBe(90);
  });

  test("every backend status has UI metadata (never color-alone: text always rendered)", () => {
    const backend = ["QUEUED", "ANALYZING", "EXTRACTING", "RENDERING", "OCR", "STRUCTURING", "VERIFYING", "CHUNKING", "INDEXING", "COMPLETED", "COMPLETED_WITH_WARNINGS", "REQUIRES_REVIEW", "FAILED", "CANCELLED"];
    for (const s of backend) expect(JOB_STATUS_META[s]).toBeDefined();
    for (const s of ["PENDING", "QUEUED", "OCR_DONE", "INDEXED", "NEEDS_REVIEW", "FAILED"]) {
      expect(PAGE_STATUS_META[s]).toBeDefined();
    }
  });
});

describe("review audit helpers", () => {
  test("pageReviewReasons parses safely, caps at 8", () => {
    expect(pageReviewReasons(null)).toEqual([]);
    expect(pageReviewReasons("{broken")).toEqual([]);
    expect(pageReviewReasons("{}")).toEqual([]);
    expect(pageReviewReasons(JSON.stringify({ reasons: ["a", "b"] }))).toEqual(["a", "b"]);
    expect(pageReviewReasons(JSON.stringify({ reasons: [1, "x", null] }))).toEqual(["x"]);
    const many = JSON.stringify({ reasons: ["r0", "r1", "r2", "r3", "r4", "r5", "r6", "r7", "r8", "r9"] });
    expect(pageReviewReasons(many)).toHaveLength(8);
  });

  test("pageReviewedFrom reads the verify trail", () => {
    expect(pageReviewedFrom(null)).toBeNull();
    expect(pageReviewedFrom("{}")).toBeNull();
    expect(pageReviewedFrom(JSON.stringify({ review: { from: "secondary", at: "2026-09-28T00:00:00Z" } }))).toBe(
      "secondary · 2026-09-28"
    );
    expect(pageReviewedFrom(JSON.stringify({ review: { from: "manual" } }))).toBe("manual");
  });
});
