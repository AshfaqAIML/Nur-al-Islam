import { NextRequest, NextResponse } from "next/server";
import { db } from "@/lib/db";
import { rateLimitByIp, tooMany } from "@/lib/rate-limit";
import {
  ACTIVE_JOB_STATUSES,
  canTransitionJob,
  cancelJob,
  computeProgress,
  retryJob,
  summarizePages,
} from "@/lib/book-processing";
import { refreshJobCounters, setBookOcrFromJob } from "@/lib/book-jobs.server";

/**
 * Book processing jobs (Phase 2 — orchestration foundation, no OCR yet).
 *
 * POST   { bookId, totalPages?, volume?, metadata? }  create job (+ PENDING page stubs)
 * GET    ?jobId=   job status + live page summary
 * GET    ?bookId=  recent jobs for a book
 * PATCH  { jobId, action: "advance" | "cancel" | "retry", to? }
 *        advance: worker-facing forward transition (validated by canTransitionJob)
 *        cancel:  any non-terminal state → CANCELLED
 *        retry:   FAILED | REQUIRES_REVIEW | COMPLETED_WITH_WARNINGS → QUEUED (+ FAILED pages → PENDING)
 *
 * All methods require the admin key (tighter than admin/resource, whose GET is open).
 */
import { checkAdmin } from "@/lib/admin-auth";

function rl(req: NextRequest) {
  const r = rateLimitByIp(req, "ingest", 30);
  return r.ok ? null : tooMany(r.retryAfter);
}

export async function GET(req: NextRequest) {
  const limited = rl(req);
  if (limited) return limited;
  if (!checkAdmin(req)) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  const jobId = req.nextUrl.searchParams.get("jobId");
  const bookId = req.nextUrl.searchParams.get("bookId");
  try {
    if (jobId) {
      const job = await db.bookProcessingJob.findUnique({
        where: { id: jobId },
        include: { book: { select: { id: true, slug: true, titleEn: true, ocrStatus: true } } },
      });
      if (!job) return NextResponse.json({ error: "Job not found" }, { status: 404 });
      const pages = await db.bookPage.findMany({
        where: { bookId: job.bookId },
        select: { status: true },
      });
      const summary = summarizePages(pages);
      return NextResponse.json({ job, summary: { ...summary, progress: computeProgress(summary) } });
    }
    if (bookId) {
      const jobs = await db.bookProcessingJob.findMany({
        where: { bookId },
        orderBy: { createdAt: "desc" },
        take: 20,
      });
      return NextResponse.json({ jobs });
    }
    return NextResponse.json({ error: "Provide ?jobId= or ?bookId=" }, { status: 400 });
  } catch {
    return NextResponse.json({ error: "Failed to load job." }, { status: 500 });
  }
}

export async function POST(req: NextRequest) {
  const limited = rl(req);
  if (limited) return limited;
  if (!checkAdmin(req)) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  let body: { bookId?: string; totalPages?: number; volume?: number; metadata?: Record<string, unknown> };
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON" }, { status: 400 });
  }
  const { bookId } = body;
  const volume = body.volume ?? 1;
  const totalPages = body.totalPages ?? 0;
  if (!bookId) return NextResponse.json({ error: "bookId is required" }, { status: 400 });
  if (!Number.isInteger(volume) || volume < 1) {
    return NextResponse.json({ error: "volume must be a positive integer" }, { status: 400 });
  }
  if (!Number.isInteger(totalPages) || totalPages < 0 || totalPages > 10000) {
    return NextResponse.json({ error: "totalPages must be an integer 0..10000" }, { status: 400 });
  }
  try {
    const book = await db.book.findUnique({ where: { id: bookId }, select: { id: true } });
    if (!book) return NextResponse.json({ error: "Book not found" }, { status: 404 });
    const active = await db.bookProcessingJob.findFirst({
      where: { bookId, status: { in: [...ACTIVE_JOB_STATUSES] } },
      select: { id: true, status: true },
    });
    if (active) {
      return NextResponse.json({ error: "An active job already exists for this book.", jobId: active.id }, { status: 409 });
    }
    // Idempotent page stubs + counters + mirror in ONE transaction: a crash
    // mid-create can never leave a job without its pages or vice versa.
    const job = await db.$transaction(async (tx) => {
      const created = await tx.bookProcessingJob.create({
        data: {
          bookId,
          status: "QUEUED",
          stage: "QUEUED",
          metadata: body.metadata ? JSON.stringify(body.metadata).slice(0, 4000) : null,
        },
      });
      if (totalPages > 0) {
        const existing = await tx.bookPage.findMany({
          where: { bookId, volume },
          select: { pageNumber: true },
        });
        const have = new Set(existing.map((p) => p.pageNumber));
        const missing: number[] = [];
        for (let n = 1; n <= totalPages; n++) if (!have.has(n)) missing.push(n);
        if (missing.length > 0) {
          await tx.bookPage.createMany({
            data: missing.map((pageNumber) => ({ bookId, volume, pageNumber, status: "PENDING" })),
          });
        }
        const count = await tx.bookPage.count({ where: { bookId } });
        await tx.bookProcessingJob.update({ where: { id: created.id }, data: { totalPages: count } });
      }
      await setBookOcrFromJob(bookId, "QUEUED", tx);
      return created;
    });
    const created = await db.bookProcessingJob.findUnique({ where: { id: job.id } });
    return NextResponse.json({ job: created }, { status: 201 });
  } catch {
    return NextResponse.json({ error: "Failed to create job." }, { status: 500 });
  }
}

export async function PATCH(req: NextRequest) {
  const limited = rl(req);
  if (limited) return limited;
  if (!checkAdmin(req)) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  let body: { jobId?: string; action?: string; to?: string };
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON" }, { status: 400 });
  }
  const { jobId, action } = body;
  if (!jobId || !action) return NextResponse.json({ error: "jobId and action are required" }, { status: 400 });
  try {
    const job = await db.bookProcessingJob.findUnique({ where: { id: jobId } });
    if (!job) return NextResponse.json({ error: "Job not found" }, { status: 404 });
    const now = new Date();
    if (action === "cancel") {
      const target = cancelJob(job.status);
      if (!target) return NextResponse.json({ error: `Cannot cancel a job in status ${job.status}.` }, { status: 409 });
      await db.$transaction(async (tx) => {
        await tx.bookProcessingJob.update({
          where: { id: jobId },
          data: { status: target, stage: target, completedAt: now, error: job.error ?? "Cancelled by admin." },
        });
        await setBookOcrFromJob(job.bookId, target, tx);
      });
    } else if (action === "retry") {
      const target = retryJob(job.status);
      if (!target) {
        return NextResponse.json({ error: `Only FAILED, REQUIRES_REVIEW or COMPLETED_WITH_WARNINGS jobs can be retried (current: ${job.status}).` }, { status: 409 });
      }
      // Resume: requeue failed pages so the next worker pass picks them up.
      await db.$transaction(async (tx) => {
        await tx.bookPage.updateMany({
          where: { bookId: job.bookId, status: "FAILED" },
          data: { status: "PENDING", error: null },
        });
        await tx.bookProcessingJob.update({
          where: { id: jobId },
          data: { status: target, stage: target, completedAt: null, error: null, failedPages: 0 },
        });
        await setBookOcrFromJob(job.bookId, target, tx);
      });
    } else if (action === "advance") {
      const to = (body.to ?? "").toString();
      if (!canTransitionJob(job.status, to)) {
        return NextResponse.json({ error: `Illegal transition ${job.status} → ${to || "(empty)"}.` }, { status: 409 });
      }
      const data: Record<string, unknown> = { status: to, stage: to };
      if (job.status === "QUEUED") data.startedAt = now;
      if (["COMPLETED", "COMPLETED_WITH_WARNINGS", "REQUIRES_REVIEW", "FAILED", "CANCELLED"].includes(to)) {
        data.completedAt = now;
      }
      await db.bookProcessingJob.update({ where: { id: jobId }, data });
      await setBookOcrFromJob(job.bookId, to);
    } else {
      return NextResponse.json({ error: 'action must be "advance", "cancel" or "retry"' }, { status: 400 });
    }
    const updated = await refreshJobCounters(jobId);
    return NextResponse.json({ job: updated });
  } catch {
    return NextResponse.json({ error: "Failed to update job." }, { status: 500 });
  }
}
