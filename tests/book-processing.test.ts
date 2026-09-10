/**
 * Phase 2 tests — book processing job state machine (pure logic).
 * Run: bun test tests/book-processing.test.ts
 * (Route-level tests need node_modules + DB; see docs/BOOK_PROCESSING_FOUNDATION.md.)
 */
import { describe, expect, test } from "bun:test";
import {
  ACTIVE_JOB_STATUSES,
  TERMINAL_JOB_STATUSES,
  cancelJob,
  canTransitionJob,
  computeProgress,
  deriveFinishedStatus,
  isJobStatus,
  isPageStatus,
  retryJob,
  summarizePages,
} from "../src/lib/book-processing";

describe("job status vocabulary", () => {
  test("terminal states are COMPLETED, COMPLETED_WITH_WARNINGS, FAILED, CANCELLED", () => {
    expect([...TERMINAL_JOB_STATUSES].sort()).toEqual(
      ["CANCELLED", "COMPLETED", "COMPLETED_WITH_WARNINGS", "FAILED"].sort(),
    );
  });

  test("active states exclude terminals and include pipeline stages", () => {
    for (const t of TERMINAL_JOB_STATUSES) expect(ACTIVE_JOB_STATUSES).not.toContain(t);
    for (const s of ["QUEUED", "ANALYZING", "OCR", "INDEXING", "REQUIRES_REVIEW"]) {
      expect(ACTIVE_JOB_STATUSES).toContain(s);
    }
  });

  test("guards reject unknown values", () => {
    expect(isJobStatus("QUEUED")).toBe(true);
    expect(isJobStatus("DONE")).toBe(false);
    expect(isJobStatus("")).toBe(false);
    expect(isPageStatus("PENDING")).toBe(true);
    expect(isPageStatus("QUEUED")).toBe(true);
    expect(isPageStatus("DONE")).toBe(false);
  });
});

describe("state transitions", () => {
  test("happy path forward chain is legal", () => {
    const chain = ["QUEUED", "ANALYZING", "EXTRACTING", "RENDERING", "OCR", "STRUCTURING", "VERIFYING", "CHUNKING", "INDEXING", "COMPLETED"];
    for (let i = 0; i < chain.length - 1; i++) {
      expect(canTransitionJob(chain[i], chain[i + 1])).toBe(true);
    }
  });

  test("skips and backward jumps are illegal", () => {
    expect(canTransitionJob("QUEUED", "OCR")).toBe(false);
    expect(canTransitionJob("OCR", "QUEUED")).toBe(false);
    expect(canTransitionJob("INDEXING", "ANALYZING")).toBe(false);
    expect(canTransitionJob("QUEUED", "COMPLETED")).toBe(false);
  });

  test("terminal states have no outgoing transitions", () => {
    for (const t of TERMINAL_JOB_STATUSES) {
      expect(canTransitionJob(t, "QUEUED")).toBe(false);
      expect(canTransitionJob(t, "ANALYZING")).toBe(false);
    }
  });

  test("review loop transitions", () => {
    expect(canTransitionJob("VERIFYING", "REQUIRES_REVIEW")).toBe(true);
    expect(canTransitionJob("REQUIRES_REVIEW", "VERIFYING")).toBe(true);
    expect(canTransitionJob("REQUIRES_REVIEW", "COMPLETED_WITH_WARNINGS")).toBe(true);
    expect(canTransitionJob("INDEXING", "COMPLETED_WITH_WARNINGS")).toBe(true);
  });

  test("failure/cancel edges exist from every active state", () => {
    for (const s of ACTIVE_JOB_STATUSES) {
      expect(canTransitionJob(s, "FAILED")).toBe(true);
      expect(canTransitionJob(s, "CANCELLED")).toBe(true);
    }
  });

  test("unknown statuses never transition", () => {
    expect(canTransitionJob("QUEUED", "NOPE")).toBe(false);
    expect(canTransitionJob("NOPE", "QUEUED")).toBe(false);
  });
});

describe("cancellation", () => {
  test("any active state cancels", () => {
    for (const s of ACTIVE_JOB_STATUSES) expect(cancelJob(s)).toBe("CANCELLED");
  });

  test("terminal and unknown states cannot cancel", () => {
    for (const t of TERMINAL_JOB_STATUSES) expect(cancelJob(t)).toBeNull();
    expect(cancelJob("NOPE")).toBeNull();
  });
});

describe("retry (resume entry)", () => {
  test("FAILED, REQUIRES_REVIEW, COMPLETED_WITH_WARNINGS requeue", () => {
    expect(retryJob("FAILED")).toBe("QUEUED");
    expect(retryJob("REQUIRES_REVIEW")).toBe("QUEUED");
    expect(retryJob("COMPLETED_WITH_WARNINGS")).toBe("QUEUED");
  });

  test("COMPLETED, CANCELLED and active states never retry", () => {
    expect(retryJob("COMPLETED")).toBeNull();
    expect(retryJob("CANCELLED")).toBeNull();
    expect(retryJob("QUEUED")).toBeNull();
    expect(retryJob("OCR")).toBeNull();
    expect(retryJob("NOPE")).toBeNull();
  });
});

describe("progress + page summary (resume source of truth)", () => {
  test("computeProgress guards divide-by-zero and clamps", () => {
    expect(computeProgress({ totalPages: 0, processedPages: 0, failedPages: 0, reviewPages: 0 })).toBe(0);
    expect(computeProgress({ totalPages: 4, processedPages: 1, failedPages: 0, reviewPages: 0 })).toBe(0.25);
    expect(computeProgress({ totalPages: 4, processedPages: 9, failedPages: 0, reviewPages: 0 })).toBe(1);
    expect(computeProgress({ totalPages: 4, processedPages: -2, failedPages: 0, reviewPages: 0 })).toBe(0);
  });

  test("summarizePages counts + identifies resumable work", () => {
    const s = summarizePages([
      { status: "OCR_DONE" },
      { status: "INDEXED" },
      { status: "FAILED" },
      { status: "NEEDS_REVIEW" },
      { status: "PENDING" },
      { status: "QUEUED" },
    ]);
    expect(s).toEqual({ totalPages: 6, processedPages: 2, failedPages: 1, reviewPages: 1, resumable: 3 });
  });

  test("empty page list summarizes to zeros", () => {
    expect(summarizePages([])).toEqual({ totalPages: 0, processedPages: 0, failedPages: 0, reviewPages: 0, resumable: 0 });
  });

  test("deriveFinishedStatus prioritizes failure, then review", () => {
    expect(deriveFinishedStatus({ totalPages: 3, processedPages: 2, failedPages: 1, reviewPages: 1 })).toBe("FAILED");
    expect(deriveFinishedStatus({ totalPages: 3, processedPages: 2, failedPages: 0, reviewPages: 1 })).toBe("REQUIRES_REVIEW");
    expect(
      deriveFinishedStatus({ totalPages: 3, processedPages: 2, failedPages: 0, reviewPages: 1 }, { warningsOk: true }),
    ).toBe("COMPLETED_WITH_WARNINGS");
    expect(deriveFinishedStatus({ totalPages: 3, processedPages: 3, failedPages: 0, reviewPages: 0 })).toBe("COMPLETED");
  });
});

/* Route-level authorization (401 without x-admin-key on all ingest/pages
   methods) is enforced in src/app/api/admin/ingest/route.ts and
   src/app/api/admin/pages/route.ts and is covered by the integration
   checklist in docs/BOOK_PROCESSING_FOUNDATION.md once node_modules + DB
   are available — route modules import next/server + Prisma and cannot run
   under dependency-free bun test. */
