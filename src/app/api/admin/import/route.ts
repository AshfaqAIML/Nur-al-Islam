import { NextRequest, NextResponse } from "next/server";
import { randomUUID } from "crypto";
import { mkdir, unlink, writeFile } from "node:fs/promises";
import path from "path";
import { db } from "@/lib/db";
import { rateLimitByIp, tooMany } from "@/lib/rate-limit";
import {
  hasPdfSignature,
  maxUploadBytes,
  resolveSourceRef,
  sha256Hex,
  slugWithSuffix,
  sourceRefFor,
  storageRoot,
} from "@/lib/book-import";

/**
 * Real PDF import (Phase 8) — multipart/form-data ONLY (never Base64 JSON).
 * Fields: pdf (File, required) + title (required for new books) + titleUr?
 * + titleAr? + language? + publisher? + edition? + volumes? + authorId?
 * + bookId? (must reference an existing Book).
 *
 * Flow: auth → size cap → magic bytes → sha256 → duplicate check (409, no
 * overwrite) → Book create-or-verify → write storage/books/{id}/original.pdf
 * → sourceRef+checksum on Book. IMPORT only — processing starts separately
 * (POST /api/admin/ingest or the Python worker --create-job).
 */
import { checkAdmin } from "@/lib/admin-auth";

export async function POST(req: NextRequest) {
  const rl = rateLimitByIp(req, "import", 10);
  if (!rl.ok) return tooMany(rl.retryAfter);
  if (!checkAdmin(req)) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  const requestId = randomUUID().slice(0, 8);

  let form: FormData;
  try {
    form = await req.formData();
  } catch {
    return NextResponse.json({ error: "Expected multipart/form-data with a pdf field." }, { status: 400 });
  }
  const file = form.get("pdf");
  if (!file || typeof file === "string" || typeof (file as File).arrayBuffer !== "function") {
    return NextResponse.json({ error: "Missing pdf file field." }, { status: 400 });
  }
  const pdf = file as unknown as File;
  const limit = maxUploadBytes();
  if (pdf.size > limit) {
    return NextResponse.json({ error: `PDF exceeds the ${Math.round(limit / 1048576)} MB limit.` }, { status: 413 });
  }
  if (pdf.size === 0) {
    return NextResponse.json({ error: "Empty file." }, { status: 400 });
  }

  let bytes: Buffer;
  try {
    bytes = Buffer.from(await pdf.arrayBuffer());
  } catch {
    return NextResponse.json({ error: "Could not read upload." }, { status: 400 });
  }
  // Client size is untrusted — re-check actual bytes; magic bytes, not MIME.
  if (bytes.length > limit) {
    return NextResponse.json({ error: `PDF exceeds the ${Math.round(limit / 1048576)} MB limit.` }, { status: 413 });
  }
  if (!hasPdfSignature(bytes.subarray(0, 8))) {
    return NextResponse.json({ error: "Not a PDF file (signature mismatch)." }, { status: 415 });
  }
  const checksum = sha256Hex(bytes);

  const str = (k: string, max = 300) => {
    const v = form.get(k);
    return typeof v === "string" ? v.trim().slice(0, max) : "";
  };
  try {
    // Duplicate source? Never overwrite, never delete — return existing.
    const dupe = await db.book.findFirst({ where: { sourceChecksum: checksum }, select: { id: true, slug: true, titleEn: true } });
    if (dupe) {
      console.info(`[import:${requestId}] duplicate checksum=${checksum.slice(0, 16)} book=${dupe.id} bytes=${bytes.length}`);
      return NextResponse.json({ duplicate: true, book: dupe }, { status: 409 });
    }

    let book = null as null | { id: string; slug: string; titleEn: string };
    let created = false;
    const bookId = str("bookId", 64);
    if (bookId) {
      book = await db.book.findUnique({ where: { id: bookId }, select: { id: true, slug: true, titleEn: true } });
      if (!book) return NextResponse.json({ error: "bookId does not match an existing Book." }, { status: 404 });
    } else {
      const titleEn = str("title", 300);
      if (!titleEn) return NextResponse.json({ error: "title is required for a new Book." }, { status: 400 });
      const volumesRaw = str("volumes", 8);
      const volumes = volumesRaw === "" ? 1 : Number(volumesRaw);
      if (!Number.isInteger(volumes) || volumes < 1 || volumes > 200) {
        return NextResponse.json({ error: "volumes must be an integer 1..200." }, { status: 400 });
      }
      const authorId = str("authorId", 64);
      if (authorId) {
        const scholar = await db.scholar.findUnique({ where: { id: authorId }, select: { id: true } });
        if (!scholar) return NextResponse.json({ error: "authorId does not match a Scholar." }, { status: 404 });
      }
      book = await db.book.create({
        data: {
          slug: slugWithSuffix(titleEn),
          titleEn,
          titleUr: str("titleUr", 300) || null,
          titleAr: str("titleAr", 300) || null,
          language: str("language", 60) || null,
          publisher: str("publisher", 200) || null,
          edition: str("edition", 120) || null,
          volumes,
          authorId: authorId || null,
        },
        select: { id: true, slug: true, titleEn: true },
      });
      created = true;
    }

    // Deterministic server-side path (client filename never trusted).
    const sourceRef = sourceRefFor(book.id);
    const absPath = resolveSourceRef(sourceRef, storageRoot());
    try {
      await mkdir(path.dirname(absPath), { recursive: true });
      await writeFile(absPath, bytes, { flag: "wx" });
    } catch (err) {
      const exists = err instanceof Error && "code" in err && (err as { code?: string }).code === "EEXIST";
      try { await unlink(absPath); } catch { /* partial already gone */ }
      // A just-created book with no stored file is a true orphan → remove it.
      // Pre-existing books are always kept (trusted sources are never deleted).
      if (created) {
        try { await db.book.delete({ where: { id: book.id } }); } catch { /* keep sick row visible */ }
      }
      if (exists) {
        return NextResponse.json({ error: "An original is already stored for this book — duplicates are never overwritten." }, { status: 409 });
      }
      console.error(`[import:${requestId}] storage write failed book=${book.id}:`, err instanceof Error ? err.message : err);
      return NextResponse.json({ error: "Could not store the original PDF." }, { status: 500 });
    }
    // "wx" refuses if a file somehow exists (no silent overwrite of originals).
    await db.book.update({ where: { id: book.id }, data: { sourceRef, sourceChecksum: checksum } });
    console.info(`[import:${requestId}] stored book=${book.id} bytes=${bytes.length} checksum=${checksum.slice(0, 16)}`);
    return NextResponse.json({ duplicate: false, book, sourceRef, checksum }, { status: 201 });
  } catch (err) {
    console.error(`[import:${requestId}] import failed:`, err instanceof Error ? err.message : err);
    return NextResponse.json({ error: "Import failed." }, { status: 500 });
  }
}
