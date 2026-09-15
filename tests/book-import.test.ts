/** Phase 8 tests — import validation (pure helpers, no fs writes). */
import { describe, expect, test } from "bun:test";
import {
  assertSafeBookId,
  hasPdfSignature,
  maxUploadBytes,
  resolveSourceRef,
  sha256Hex,
  slugify,
  slugWithSuffix,
  sourceRefFor,
  storageRoot,
} from "../src/lib/book-import";

describe("PDF validation", () => {
  test("magic bytes, not MIME", () => {
    expect(hasPdfSignature(Buffer.from("%PDF-1.7 rest"))).toBe(true);
    expect(hasPdfSignature(Buffer.from("%PDF-"))).toBe(true);
    expect(hasPdfSignature(Buffer.from("PK\x03\x04"))).toBe(false);
    expect(hasPdfSignature(Buffer.from(""))).toBe(false);
    expect(hasPdfSignature(Buffer.from("  %PDF-1.4"))).toBe(false); // leading junk rejected
    expect(hasPdfSignature(new Uint8Array([0x25, 0x50, 0x44, 0x46, 0x2d]))).toBe(true);
  });

  test("checksum stable", () => {
    expect(sha256Hex(Buffer.from("abc"))).toBe("ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad");
    expect(sha256Hex(Buffer.from("abc"))).toBe(sha256Hex(Buffer.from("abc")));
  });

  test("size limit env-configurable, bounded", () => {
    expect(maxUploadBytes()).toBe(100 * 1024 * 1024);
  });
});

describe("storage paths (never client-controlled)", () => {
  test("sourceRef stable + deterministic", () => {
    expect(sourceRefFor("cmabc123xyz")).toBe("books/cmabc123xyz/original.pdf");
    expect(sourceRefFor("cmabc123xyz")).toBe(sourceRefFor("cmabc123xyz"));
  });

  test("unsafe ids rejected", () => {
    for (const bad of ["../x", "/abs", "a/b", "", "x", "a".repeat(65), "a b"]) {
      expect(() => assertSafeBookId(bad)).toThrow();
    }
    expect(() => sourceRefFor("../../etc/passwd")).toThrow();
  });

  test("resolveSourceRef contains traversal, hides absolutes", () => {
    const root = storageRoot();
    expect(resolveSourceRef("books/abc/original.pdf", root)).toContain("original.pdf");
    expect(() => resolveSourceRef("/etc/passwd", root)).toThrow();
    expect(() => resolveSourceRef("../outside.pdf", root)).toThrow();
    expect(() => resolveSourceRef("books/../../x.pdf", root)).toThrow();
    expect(() => resolveSourceRef("", root)).toThrow();
  });

  test("slug helpers", () => {
    expect(slugify("Fatawa Razvia Vol 4")).toBe("fatawa-razvia-vol-4");
    expect(slugify("!!!")).toBe("item");
    expect(slugWithSuffix("X")).toMatch(/^x-[a-z0-9]{4}$/);
  });
});
