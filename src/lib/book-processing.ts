/**
 * Book processing orchestration — pure state-machine helpers (Phase 2).
 *
 * No Prisma / Next imports here on purpose: this module is unit-tested with
 * `bun test` and reused by the ingest API routes. SQLite convention from
 * prisma/schema.prisma is preserved: statuses are plain strings, documented
 * by these constant lists (no native enums).
 */

/** All BookProcessingJob.status values. */
export const JOB_STATUSES = [
  "QUEUED",
  "ANALYZING",
  "EXTRACTING",
  "RENDERING",
  "OCR",
  "STRUCTURING",
  "VERIFYING",
  "CHUNKING",
  "INDEXING",
  "COMPLETED",
  "COMPLETED_WITH_WARNINGS",
  "REQUIRES_REVIEW",
  "FAILED",
  "CANCELLED",
] as const;
export type JobStatus = (typeof JOB_STATUSES)[number];

/** Terminal states — a job in one of these performs no further work. */
export const TERMINAL_JOB_STATUSES: readonly JobStatus[] = [
  "COMPLETED",
  "COMPLETED_WITH_WARNINGS",
  "FAILED",
  "CANCELLED",
];

/** Non-terminal states. */
export const ACTIVE_JOB_STATUSES: readonly JobStatus[] = JOB_STATUSES.filter(
  (s): s is JobStatus => !(TERMINAL_JOB_STATUSES as readonly string[]).includes(s),
);

/**
 * Allowed forward transitions. Terminal states have no outgoing edges here;
 * `retryJob` / `cancelJob` below handle the explicit terminal operations.
 */
const JOB_TRANSITIONS: Record<JobStatus, readonly JobStatus[]> = {
  QUEUED: ["ANALYZING", "CANCELLED", "FAILED"],
  ANALYZING: ["EXTRACTING", "FAILED", "CANCELLED"],
  EXTRACTING: ["RENDERING", "FAILED", "CANCELLED"],
  RENDERING: ["OCR", "FAILED", "CANCELLED"],
  OCR: ["STRUCTURING", "FAILED", "CANCELLED"],
  STRUCTURING: ["VERIFYING", "FAILED", "CANCELLED"],
  VERIFYING: ["CHUNKING", "REQUIRES_REVIEW", "FAILED", "CANCELLED"],
  CHUNKING: ["INDEXING", "FAILED", "CANCELLED"],
  INDEXING: ["COMPLETED", "COMPLETED_WITH_WARNINGS", "REQUIRES_REVIEW", "FAILED", "CANCELLED"],
  COMPLETED: [],
  COMPLETED_WITH_WARNINGS: [],
  REQUIRES_REVIEW: ["VERIFYING", "COMPLETED_WITH_WARNINGS", "FAILED", "CANCELLED"],
  FAILED: [],
  CANCELLED: [],
};

/** All BookPage.status values (page-level processing state). */
export const PAGE_STATUSES = [
  "PENDING",
  "QUEUED",
  "OCR_DONE",
  "INDEXED",
  "NEEDS_REVIEW",
  "FAILED",
] as const;
export type PageStatus = (typeof PAGE_STATUSES)[number];

/** Page states that still need work when resuming a job. */
export const RESUMABLE_PAGE_STATUSES: readonly PageStatus[] = ["PENDING", "QUEUED", "FAILED"];

/** Page states counted as successfully processed. */
export const DONE_PAGE_STATUSES: readonly PageStatus[] = ["OCR_DONE", "INDEXED"];

export function isJobStatus(s: string): s is JobStatus {
  return (JOB_STATUSES as readonly string[]).includes(s);
}

export function isPageStatus(s: string): s is PageStatus {
  return (PAGE_STATUSES as readonly string[]).includes(s);
}

export function isTerminalJobStatus(s: string): boolean {
  return (TERMINAL_JOB_STATUSES as readonly string[]).includes(s);
}

/** True when `to` is a legal forward transition from `from`. Unknown values → false. */
export function canTransitionJob(from: string, to: string): boolean {
  if (!isJobStatus(from) || !isJobStatus(to)) return false;
  return JOB_TRANSITIONS[from].includes(to);
}

/**
 * Cancel is legal from any non-terminal state. Returns the target status
 * ("CANCELLED") or null when cancellation is not allowed.
 */
export function cancelJob(from: string): JobStatus | null {
  if (!isJobStatus(from) || isTerminalJobStatus(from)) return null;
  return "CANCELLED";
}

/**
 * Retry re-queues a job that ended FAILED, REQUIRES_REVIEW, or
 * COMPLETED_WITH_WARNINGS. Returns "QUEUED" or null when not allowed.
 * Completed / cancelled jobs are never retried (create a new job instead).
 */
export function retryJob(from: string): JobStatus | null {
  if (from === "FAILED" || from === "REQUIRES_REVIEW" || from === "COMPLETED_WITH_WARNINGS") {
    return "QUEUED";
  }
  return null;
}

export interface JobCounters {
  totalPages: number;
  processedPages: number;
  failedPages: number;
  reviewPages: number;
}

/** progress ∈ [0,1]: processed / total, guarded against total = 0. */
export function computeProgress(c: JobCounters): number {
  if (c.totalPages <= 0) return 0;
  const p = c.processedPages / c.totalPages;
  return Math.min(1, Math.max(0, p));
}

export interface PageLike {
  status: string;
}

/**
 * Recompute counters from a page list (source of truth for resume).
 * - processed: OCR_DONE | INDEXED
 * - failed: FAILED
 * - review: NEEDS_REVIEW
 * - resumable: PENDING | QUEUED | FAILED
 */
export function summarizePages(pages: PageLike[]): JobCounters & { resumable: number } {
  let processedPages = 0;
  let failedPages = 0;
  let reviewPages = 0;
  let resumable = 0;
  for (const p of pages) {
    if ((DONE_PAGE_STATUSES as readonly string[]).includes(p.status)) processedPages++;
    else if (p.status === "FAILED") failedPages++;
    else if (p.status === "NEEDS_REVIEW") reviewPages++;
    if ((RESUMABLE_PAGE_STATUSES as readonly string[]).includes(p.status)) resumable++;
  }
  return { totalPages: pages.length, processedPages, failedPages, reviewPages, resumable };
}

/**
 * Derive the finished status from counters once no resumable pages remain:
 * failed > 0 → FAILED · review > 0 → REQUIRES_REVIEW (or COMPLETED_WITH_WARNINGS
 * when everything else processed — caller picks via `warningsOk`) · else COMPLETED.
 */
export function deriveFinishedStatus(
  c: JobCounters,
  opts?: { warningsOk?: boolean },
): Extract<JobStatus, "COMPLETED" | "COMPLETED_WITH_WARNINGS" | "REQUIRES_REVIEW" | "FAILED"> {
  if (c.failedPages > 0) return "FAILED";
  if (c.reviewPages > 0) return opts?.warningsOk ? "COMPLETED_WITH_WARNINGS" : "REQUIRES_REVIEW";
  return "COMPLETED";
}
