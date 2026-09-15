/**
 * Book import helpers — pure, unit-tested (Phase 8).
 * Storage convention: STORAGE_ROOT/books/{bookId}/original.pdf (server-side,
 * gitignored, never web-served). sourceRef is the STABLE relative reference
 * `books/{bookId}/original.pdf` — never an absolute path, never client input.
 */
import { createHash } from "crypto";
import path from "path";

export const PDF_MAGIC = "%PDF-";
export const DEFAULT_MAX_UPLOAD_BYTES = 100 * 1024 * 1024; // 100 MB

export function maxUploadBytes(): number {
  const raw = process.env.NUR_MAX_UPLOAD_MB;
  const mb = raw !== undefined ? Number(raw) : NaN;
  if (Number.isFinite(mb) && mb > 0 && mb <= 2000) return Math.floor(mb) * 1024 * 1024;
  return DEFAULT_MAX_UPLOAD_BYTES;
}

/** First bytes must be the PDF signature (magic bytes, not MIME). */
export function hasPdfSignature(head: Uint8Array | Buffer): boolean {
  const buf = Buffer.isBuffer(head)
    ? head.subarray(0, 8)
    : Buffer.from(head.buffer, head.byteOffset, Math.min(8, head.byteLength));
  return buf.toString("latin1").startsWith(PDF_MAGIC);
}

export function sha256Hex(data: Uint8Array | Buffer): string {
  return createHash("sha256").update(Buffer.from(data)).digest("hex");
}

/** Storage root: explicit env wins (deployment volume), else project storage/. */
export function storageRoot(): string {
  return process.env.NUR_STORAGE ?? path.join(process.cwd(), "storage");
}

/**
 * Stable relative reference for a book's original. bookId must be a
 * database-issued id (cuid) — never raw client input (path traversal safe
 * by construction; validated below anyway).
 */
export function sourceRefFor(bookId: string): string {
  assertSafeBookId(bookId);
  return `books/${bookId}/original.pdf`;
}

/** Reject anything that is not a plain cuid-ish id (defense in depth). */
export function assertSafeBookId(bookId: string): void {
  if (!/^[A-Za-z0-9_-]{8,64}$/.test(bookId)) {
    throw new Error("Unsafe book id for storage path");
  }
}

/** Absolute disk path for a sourceRef. Rejects absolute refs and `..`. */
export function resolveSourceRef(sourceRef: string, root?: string): string {
  const base = root ?? storageRoot();
  if (path.isAbsolute(sourceRef)) throw new Error("Absolute sourceRef rejected");
  const normalized = path.normalize(sourceRef);
  if (normalized === ".." || normalized.startsWith(`..${path.sep}`) || normalized.includes("..")) {
    throw new Error("Path traversal in sourceRef rejected");
  }
  const abs = path.resolve(base, normalized);
  const baseResolved = path.resolve(base) + path.sep;
  if (!abs.startsWith(baseResolved)) throw new Error("sourceRef escapes storage root");
  return abs;
}

/** URL-safe slug (mirrors admin/resource slugify for import-created books). */
export function slugify(s: string): string {
  const base = s
    .toLowerCase()
    .normalize("NFKD")
    .replace(/[^\p{L}\p{N}]+/gu, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 56);
  return base || "item";
}

export function slugWithSuffix(s: string): string {
  return `${slugify(s)}-${Math.random().toString(36).slice(2, 6)}`;
}
