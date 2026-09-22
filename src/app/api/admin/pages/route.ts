import { NextRequest, NextResponse } from "next/server";
import { db } from "@/lib/db";
import { rateLimitByIp, tooMany } from "@/lib/rate-limit";
import { summarizePages } from "@/lib/book-processing";
import { refreshJobCounters } from "@/lib/book-jobs.server";

/**
 * Book page processing state (Phase 2 — read + review triage).
 *
 * GET   ?jobId= | ?bookId=   page list (ordered volume, pageNumber)
 *       &reviewOnly=1        only NEEDS_REVIEW pages (review queue)
 *       &take= (default 100, max 500) &skip=
 * PATCH { pageId, action: "verify" | "requeue" | "fail" | "ocr", ... }
 *       verify:  NEEDS_REVIEW → OCR_DONE + verified=true (human approved text)
 *       requeue: NEEDS_REVIEW | FAILED → PENDING (picked up on resume)
 *       fail:    any non-terminal page → FAILED + error note
 *       ocr:     worker writeback (Phase 3) — stores extraction results and
 *                marks the page OCR_DONE. Small JSON only; PDFs/images are
 *                never sent through this endpoint.
 *
 * Page writes refresh the parent book's latest active job counters.
 * All methods require the admin key.
 */
import { checkAdmin } from "@/lib/admin-auth";

async function latestActiveJobId(bookId: string): Promise<string | null> {  const job = await db.bookProcessingJob.findFirst({
    where: {
      bookId,
      status: { in: ["QUEUED", "ANALYZING", "EXTRACTING", "RENDERING", "OCR", "STRUCTURING", "VERIFYING", "CHUNKING", "INDEXING", "REQUIRES_REVIEW"] },
    },
    orderBy: { createdAt: "desc" },
    select: { id: true },
  });
  return job?.id ?? null;
}

export async function GET(req: NextRequest) {
  const rl = rateLimitByIp(req, "ingest", 30);
  if (!rl.ok) return tooMany(rl.retryAfter);
  if (!checkAdmin(req)) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  const sp = req.nextUrl.searchParams;
  const jobId = sp.get("jobId");
  const bookIdParam = sp.get("bookId");
  const reviewOnly = sp.get("reviewOnly") === "1";
  // Phase 13: single-page detail (full text states) for the review dialog.
  // List responses stay lean; text travels only on explicit request.
  const pageId = sp.get("pageId");
  if (pageId) {
    try {
      const page = await db.bookPage.findUnique({
        where: { id: pageId },
        select: {
          id: true, volume: true, pageNumber: true, chapter: true, status: true,
          language: true, engine: true, ocrConfidence: true, verified: true,
          attempts: true, error: true, updatedAt: true,
          ocrText: true, normalizedText: true, verifiedText: true,
          ocrTextSecondary: true, engineSecondary: true, ocrConfidenceSecondary: true,
          signals: true,
        },
      });
      if (!page) return NextResponse.json({ error: "Page not found" }, { status: 404 });
      return NextResponse.json({ page });
    } catch {
      return NextResponse.json({ error: "Failed to load page." }, { status: 500 });
    }
  }
  const take = Math.min(Math.max(parseInt(sp.get("take") ?? "100", 10) || 100, 1), 500);
  const skip = Math.max(parseInt(sp.get("skip") ?? "0", 10) || 0, 0);
  try {
    let bookId = bookIdParam;
    if (jobId) {
      const job = await db.bookProcessingJob.findUnique({ where: { id: jobId }, select: { bookId: true } });
      if (!job) return NextResponse.json({ error: "Job not found" }, { status: 404 });
      bookId = job.bookId;
    }
    if (!bookId) return NextResponse.json({ error: "Provide ?jobId= or ?bookId=" }, { status: 400 });
    const where = reviewOnly ? { bookId, status: "NEEDS_REVIEW" as const } : { bookId };
    const [pages, total, all] = await Promise.all([
      db.bookPage.findMany({
        where,
        orderBy: [{ volume: "asc" }, { pageNumber: "asc" }],
        take,
        skip,
        select: { id: true, volume: true, pageNumber: true, chapter: true, status: true, language: true, engine: true, ocrConfidence: true, verified: true, attempts: true, error: true, updatedAt: true, ocrTextSecondary: true, engineSecondary: true, ocrConfidenceSecondary: true },
      }),
      db.bookPage.count({ where }),
      db.bookPage.findMany({ where: { bookId }, select: { status: true } }),
    ]);
    const summary = summarizePages(all);
    return NextResponse.json({ pages, total, summary });
  } catch {
    return NextResponse.json({ error: "Failed to load pages." }, { status: 500 });
  }
}

/** Merge a patch object into the signals JSON without dropping existing keys. */
function mergeSignals(current: string | null, patch: Record<string, unknown>): string | null {
  let base: Record<string, unknown> = {};
  if (current) {
    try {
      const v: unknown = JSON.parse(current);
      if (v && typeof v === "object") base = v as Record<string, unknown>;
    } catch { /* keep base empty on corrupt JSON */ }
  }
  return JSON.stringify({ ...base, ...patch }).slice(0, 8000);
}

export async function PATCH(req: NextRequest) {
  const rl = rateLimitByIp(req, "ingest", 30);
  if (!rl.ok) return tooMany(rl.retryAfter);
  if (!checkAdmin(req)) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  let body: { pageId?: string; action?: string; error?: string; ocrText?: string; ocrConfidence?: number | null; language?: string; engine?: string; checksum?: string | null; normalizedText?: string | null; verifiedText?: string | null; signals?: string | null; needsReview?: boolean; blank?: boolean; ocrTextSecondary?: string | null; engineSecondary?: string | null; ocrConfidenceSecondary?: number | null; secondaryError?: string | null };
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON" }, { status: 400 });
  }
  const { pageId, action } = body;
  if (!pageId || !action) return NextResponse.json({ error: "pageId and action are required" }, { status: 400 });
  try {
    const page = await db.bookPage.findUnique({ where: { id: pageId } });
    if (!page) return NextResponse.json({ error: "Page not found" }, { status: 404 });
    if (action === "verify") {
      if (page.status !== "NEEDS_REVIEW") {
        return NextResponse.json({ error: `Only NEEDS_REVIEW pages can be verified (current: ${page.status}).` }, { status: 409 });
      }
      // Phase 4: optional human-corrected text → verifiedText (RAW untouched).
      // Phase 13 audit: record whether the approved text matches the primary
      // capture, the secondary capture, or neither (manual). Timestamps it.
      // (Casts bridge older generated clients until `prisma generate` reruns.)
      const approved = (body.verifiedText ?? null)?.toString().slice(0, 200000) || null;
      const row = page as typeof page & { ocrTextSecondary?: string | null };
      const from =
        approved === null ? "none"
        : approved === page.ocrText ? "primary"
        : approved === row.ocrTextSecondary ? "secondary"
        : "manual";
      await db.bookPage.update({
        where: { id: pageId },
        data: {
          status: "OCR_DONE",
          verified: true,
          error: null,
          verifiedText: approved,
          signals: mergeSignals(page.signals, { review: { at: new Date().toISOString(), from } }),
        },
      });
    } else if (action === "requeue") {
      // Phase 14: NEEDS_REVIEW|FAILED|INDEXED → PENDING. Texts preserved;
      // the page leaves the index until reprocessed + reindexed (honest).
      if (page.status !== "NEEDS_REVIEW" && page.status !== "FAILED" && page.status !== "INDEXED") {
        return NextResponse.json({ error: `Only NEEDS_REVIEW, FAILED or INDEXED pages can be requeued (current: ${page.status}).` }, { status: 409 });
      }
      await db.bookPage.update({ where: { id: pageId }, data: { status: "PENDING", error: null } });
    } else if (action === "fail") {
      if (page.status === "INDEXED") {
        return NextResponse.json({ error: "INDEXED pages cannot be marked failed." }, { status: 409 });
      }
      await db.bookPage.update({
        where: { id: pageId },
        data: { status: "FAILED", error: (body.error ?? "Marked failed by admin.").toString().slice(0, 500) },
      });
    } else if (action === "ocr") {
      // Phase 3 worker writeback (+ Phase 4 text states / review routing).
      // blank === true stores a confirmed-empty page (BLANK route) so it is
      // not reprocessed on resume; otherwise ocrText must be non-empty.
      const isBlank = body.blank === true;
      const ocrText = (body.ocrText ?? "").toString();
      if (!isBlank && !ocrText.trim()) {
        return NextResponse.json({ error: "ocrText must be non-empty (use fail for blank/illegible pages)." }, { status: 400 });
      }
      if (ocrText.length > 200000) {
        return NextResponse.json({ error: "ocrText exceeds 200000 characters." }, { status: 413 });
      }
      const ocrConfidence =
        body.ocrConfidence === null || body.ocrConfidence === undefined
          ? null
          : Number(body.ocrConfidence);
      if (ocrConfidence !== null && (!Number.isFinite(ocrConfidence) || ocrConfidence < 0 || ocrConfidence > 1)) {
        return NextResponse.json({ error: "ocrConfidence must be null or a number 0..1." }, { status: 400 });
      }
      await db.bookPage.update({
        where: { id: pageId },
        data: {
          // Phase 4 text states: this stores a fresh RAW extraction (re-OCR
          // legitimately replaces it). RAW is never mixed with corrections:
          // normalized search text goes to normalizedText, human corrections
          // go to verifiedText via the verify flow. No per-revision history
          // is kept (documented limitation).
          status: body.needsReview === true ? "NEEDS_REVIEW" : "OCR_DONE",
          ocrText,
          ocrConfidence,
          language: (body.language ?? null)?.toString().slice(0, 10) || null,
          engine: (body.engine ?? null)?.toString().slice(0, 120) || null,
          checksum: (body.checksum ?? null)?.toString().slice(0, 128) || null,
          normalizedText: (body.normalizedText ?? null)?.toString().slice(0, 200000) || null,
          signals: (body.signals ?? null)?.toString().slice(0, 8000) || null,
          attempts: { increment: 1 },
          error: body.needsReview === true ? "Flagged for review by worker." : null,
        },
      });
    } else if (action === "ocr2") {
      // Phase 13 secondary capture: stores ONLY the secondary columns.
      // Never touches raw primary, normalized, verified, or status.
      // secondaryError records a failed secondary attempt (recoverable).
      const secondaryError = (body.secondaryError ?? null)?.toString().slice(0, 500) || null;
      if (secondaryError) {
        await db.bookPage.update({
          where: { id: pageId },
          data: {
            signals: mergeSignals(page.signals, {
              secondary: { status: "failed", error: secondaryError, at: new Date().toISOString() },
            }),
          },
        });
      } else {
        const text = (body.ocrTextSecondary ?? "").toString();
        if (!text.trim()) {
          return NextResponse.json({ error: "ocrTextSecondary must be non-empty (use secondaryError to record failure)." }, { status: 400 });
        }
        if (text.length > 200000) {
          return NextResponse.json({ error: "ocrTextSecondary exceeds 200000 characters." }, { status: 413 });
        }
        const conf =
          body.ocrConfidenceSecondary === null || body.ocrConfidenceSecondary === undefined
            ? null
            : Number(body.ocrConfidenceSecondary);
        if (conf !== null && (!Number.isFinite(conf) || conf < 0 || conf > 1)) {
          return NextResponse.json({ error: "ocrConfidenceSecondary must be null or a number 0..1." }, { status: 400 });
        }
        await db.bookPage.update({
          where: { id: pageId },
          data: {
            ocrTextSecondary: text,
            engineSecondary: (body.engineSecondary ?? null)?.toString().slice(0, 120) || null,
            ocrConfidenceSecondary: conf,
            signals: mergeSignals(page.signals, {
              secondary: { status: "done", engine: (body.engineSecondary ?? null)?.toString().slice(0, 120) || null, at: new Date().toISOString() },
            }),
          },
        });
      }
    } else if (action === "retry-secondary") {
      // Clear secondary state so the next worker pass recaptures it.
      // Primary text, verification, and status are untouched.
      await db.bookPage.update({
        where: { id: pageId },
        data: {
          ocrTextSecondary: null,
          engineSecondary: null,
          ocrConfidenceSecondary: null,
          signals: mergeSignals(page.signals, {
            secondary: { status: "queued", at: new Date().toISOString() },
          }),
        },
      });
    } else {
      return NextResponse.json({ error: 'action must be "verify", "requeue", "fail", "ocr", "ocr2" or "retry-secondary"' }, { status: 400 });
    }
    const jobId = await latestActiveJobId(page.bookId);
    if (jobId) await refreshJobCounters(jobId);
    const updated = await db.bookPage.findUnique({
      where: { id: pageId },
      select: { id: true, volume: true, pageNumber: true, status: true, verified: true, error: true },
    });
    return NextResponse.json({ page: updated });
  } catch {
    return NextResponse.json({ error: "Failed to update page." }, { status: 500 });
  }
}
