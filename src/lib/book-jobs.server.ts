import type { Prisma } from "@prisma/client";
import { db } from "@/lib/db";
import { summarizePages, computeProgress } from "@/lib/book-processing";

/** Writable client: global db or an interactive-transaction client. */
export type JobDb = Prisma.TransactionClient | typeof db;

/**
 * Server-only job counter maintenance (Phase 2).
 * Page rows are the source of truth; job counters are a cached rollup.
 * Called after page writes and job transitions — never by the client directly.
 */
export async function refreshJobCounters(jobId: string, client: JobDb = db) {
  const job = await client.bookProcessingJob.findUnique({ where: { id: jobId } });
  if (!job) return null;
  const pages = await client.bookPage.findMany({
    where: { bookId: job.bookId },
    select: { status: true },
  });
  const s = summarizePages(pages);
  const progress = computeProgress(s);
  return client.bookProcessingJob.update({
    where: { id: jobId },
    data: {
      totalPages: s.totalPages,
      processedPages: s.processedPages,
      failedPages: s.failedPages,
      reviewPages: s.reviewPages,
      progress,
    },
  });
}

/** Mirror a job's lifecycle onto Book.ocrStatus (drives admin workflow cards). */
export async function setBookOcrFromJob(bookId: string, jobStatus: string, client: JobDb = db) {
  let ocrStatus: string | null = null;
  if (jobStatus === "COMPLETED" || jobStatus === "COMPLETED_WITH_WARNINGS") ocrStatus = "DONE";
  else if (jobStatus === "REQUIRES_REVIEW" || jobStatus === "FAILED") ocrStatus = "NEEDS_REVIEW";
  else if (jobStatus === "CANCELLED") {
    const active = await client.bookProcessingJob.findFirst({
      where: {
        bookId,
        status: { in: ["QUEUED", "ANALYZING", "EXTRACTING", "RENDERING", "OCR", "STRUCTURING", "VERIFYING", "CHUNKING", "INDEXING", "REQUIRES_REVIEW"] },
      },
      select: { id: true },
    });
    if (!active) ocrStatus = "NOT_STARTED";
  } else {
    ocrStatus = "IN_PROGRESS";
  }
  if (ocrStatus) await client.book.update({ where: { id: bookId }, data: { ocrStatus } });
}
