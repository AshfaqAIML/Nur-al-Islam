/**
 * Book processing contracts + typed API client (Phase 7).
 * Pure helpers (hash builders, status meta, progress) are unit-tested;
 * fetch functions follow the existing apiGet/apiAdmin conventions.
 */
import { apiAdmin, apiGet } from "@/lib/api";

const ADMIN_KEY = "nur-al-usul-admin";

/** Keyed GET (same shared-key convention as apiAdmin, which is write-only). */
async function apiAdminGet<T>(url: string): Promise<T> {
  const res = await fetch(url, { headers: { "x-admin-key": ADMIN_KEY }, cache: "no-store" });
  const json = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error((json as { error?: string }).error || `GET ${url} failed: ${res.status}`);
  return json as T;
}

// ─── Types (aligned with backend response schemas) ───

export type JobStatus =
  | "QUEUED" | "ANALYZING" | "EXTRACTING" | "RENDERING" | "OCR"
  | "STRUCTURING" | "VERIFYING" | "CHUNKING" | "INDEXING"
  | "COMPLETED" | "COMPLETED_WITH_WARNINGS" | "REQUIRES_REVIEW"
  | "FAILED" | "CANCELLED";

export type PageStatus = "PENDING" | "QUEUED" | "OCR_DONE" | "INDEXED" | "NEEDS_REVIEW" | "FAILED";

export interface ProcessingJob {
  id: string; bookId: string; status: JobStatus | string; stage: string;
  progress: number; totalPages: number; processedPages: number;
  failedPages: number; reviewPages: number;
  startedAt: string | null; completedAt: string | null; error: string | null;
  createdAt: string; updatedAt: string;
}

export interface JobSummary {
  totalPages: number; processedPages: number; failedPages: number;
  reviewPages: number; resumable: number; progress: number;
}

export interface BookPageItem {
  id: string; volume: number; pageNumber: number; chapter: string | null;
  status: PageStatus | string; language: string | null; engine: string | null;
  ocrConfidence: number | null; verified: boolean; attempts: number;
  error: string | null; updatedAt: string;
  ocrText?: string | null; normalizedText?: string | null; verifiedText?: string | null;
  ocrTextSecondary?: string | null; engineSecondary?: string | null;
  ocrConfidenceSecondary?: number | null;
  signals?: string | null;
}

/** Verification-signal reasons for the review dialog (safe parse, [] fallback). */
export function pageReviewReasons(signals: string | null | undefined): string[] {
  if (!signals) return [];
  try {
    const v: unknown = JSON.parse(signals);
    const r = (v as { reasons?: unknown }).reasons;
    return Array.isArray(r) ? r.filter((x): x is string => typeof x === "string").slice(0, 8) : [];
  } catch {
    return [];
  }
}

/** Who/what produced the verified text, per the verify audit trail. */
export function pageReviewedFrom(signals: string | null | undefined): string | null {
  if (!signals) return null;
  try {
    const v: unknown = JSON.parse(signals);
    const r = (v as { review?: unknown }).review as { from?: unknown; at?: unknown } | undefined;
    if (!r || typeof r.from !== "string") return null;
    return typeof r.at === "string" ? `${r.from} · ${r.at.slice(0, 10)}` : r.from;
  } catch {
    return null;
  }
}

export interface SourceCitation {
  id: string; sourceType: string;
  bookId: string | null; bookPageId: string | null;
  volume: string | null; page: string | null; chapter: string | null;
  quote: string | null; verificationStatus: string;
  ocrConfidence: number | null; humanVerified: boolean;
  book?: { slug: string; titleEn: string } | null;
}

// ─── Pure helpers (tested) ───

/** Deep-link hash param for a book page: book/{slug}/{pageNumber}. */
export function buildBookPageParam(slug: string, pageNumber: number): string {
  return `book/${slug}/${pageNumber}`;
}

/** Parse a sources-view param into {kind, slug, page?}. */
export function parseSourcesParam(param: string | null): { kind: string; slug: string; page: number | null } | null {
  if (!param) return null;
  const [kind, slug, pageRaw] = param.split("/");
  if ((kind !== "book" && kind !== "scholar") || !slug) return null;
  const page = pageRaw !== undefined && pageRaw !== "" ? Number(pageRaw) : null;
  return { kind, slug, page: page !== null && Number.isInteger(page) && page > 0 ? page : null };
}

/** Localized jild/volume label without manual string reversal. */
export function formatJild(volume: number | null, lang: string): string {
  if (volume === null || volume === undefined) return "";
  if (lang === "ur") return `جلد ${volume}`;
  if (lang === "ar") return `المجلد ${volume}`;
  return `Vol. ${volume}`;
}

const TERMINAL_JOB: readonly string[] = ["COMPLETED", "COMPLETED_WITH_WARNINGS", "FAILED", "CANCELLED"];

export function isTerminalJob(status: string): boolean {
  return TERMINAL_JOB.includes(status);
}

/** 0..100 progress, guarded; prefers live counters over stored progress. */
export function jobProgress(job: Pick<ProcessingJob, "progress" | "totalPages" | "processedPages">): number {
  if (job.totalPages > 0) return Math.round((job.processedPages / job.totalPages) * 100);
  return Math.round((job.progress || 0) * 100);
}

export const JOB_STATUS_META: Record<string, { tone: "emerald" | "amber" | "rose" | "stone" | "sky" }> = {
  QUEUED: { tone: "stone" }, ANALYZING: { tone: "sky" }, EXTRACTING: { tone: "sky" },
  RENDERING: { tone: "sky" }, OCR: { tone: "sky" }, STRUCTURING: { tone: "sky" },
  VERIFYING: { tone: "amber" }, CHUNKING: { tone: "sky" }, INDEXING: { tone: "sky" },
  COMPLETED: { tone: "emerald" }, COMPLETED_WITH_WARNINGS: { tone: "amber" },
  REQUIRES_REVIEW: { tone: "amber" }, FAILED: { tone: "rose" }, CANCELLED: { tone: "stone" },
};

export const PAGE_STATUS_META: Record<string, { tone: "emerald" | "amber" | "rose" | "stone" | "sky" }> = {
  PENDING: { tone: "stone" }, QUEUED: { tone: "sky" }, OCR_DONE: { tone: "emerald" },
  INDEXED: { tone: "emerald" }, NEEDS_REVIEW: { tone: "amber" }, FAILED: { tone: "rose" },
};

// ─── Typed fetch (existing conventions: apiGet public, apiAdmin keyed) ───

export async function fetchProcessingJobs(bookId?: string): Promise<{ jobs?: ProcessingJob[]; job?: ProcessingJob; summary?: JobSummary }> {
  const q = bookId ? `?bookId=${encodeURIComponent(bookId)}` : "";
  return apiAdminGet(`/api/admin/ingest${q}`);
}

export async function fetchJobStatus(jobId: string): Promise<{ job: ProcessingJob; summary: JobSummary }> {
  return apiAdminGet(`/api/admin/ingest?jobId=${encodeURIComponent(jobId)}`);
}

export async function createProcessingJob(input: { bookId: string; totalPages?: number; volume?: number; metadata?: Record<string, unknown> }): Promise<{ job: ProcessingJob }> {
  return apiAdmin("/api/admin/ingest", input, "POST");
}

export async function patchProcessingJob(jobId: string, action: "advance" | "cancel" | "retry", to?: string): Promise<{ job: ProcessingJob }> {
  return apiAdmin("/api/admin/ingest", { jobId, action, to }, "PATCH");
}

export async function fetchPages(params: { jobId?: string; bookId?: string; reviewOnly?: boolean; take?: number; skip?: number }): Promise<{ pages: BookPageItem[]; total: number; summary: JobSummary }> {
  const sp = new URLSearchParams();
  if (params.jobId) sp.set("jobId", params.jobId);
  if (params.bookId) sp.set("bookId", params.bookId);
  if (params.reviewOnly) sp.set("reviewOnly", "1");
  if (params.take !== undefined) sp.set("take", String(params.take));
  if (params.skip) sp.set("skip", String(params.skip));
  return apiAdminGet(`/api/admin/pages?${sp.toString()}`);
}

/** Full single-page record (all text states) for the review dialog. */
export async function fetchPageDetail(pageId: string): Promise<{ page: BookPageItem }> {
  return apiAdminGet(`/api/admin/pages?pageId=${encodeURIComponent(pageId)}`);
}

export async function patchPage(pageId: string, action: "verify" | "requeue" | "fail" | "retry-secondary", extra?: { verifiedText?: string; error?: string }): Promise<{ page: BookPageItem }> {
  return apiAdmin("/api/admin/pages", { pageId, action, ...extra }, "PATCH");
}

export async function writePageSecondary(
  pageId: string,
  payload: { ocrTextSecondary?: string; engineSecondary?: string; ocrConfidenceSecondary?: number | null; secondaryError?: string },
): Promise<{ page: BookPageItem }> {
  return apiAdmin("/api/admin/pages", { pageId, action: "ocr2", ...payload }, "PATCH");
}

export async function writePageOcr(pageId: string, payload: { ocrText?: string; ocrConfidence?: number | null; language?: string; engine?: string; checksum?: string | null; normalizedText?: string | null; signals?: string | null; needsReview?: boolean; blank?: boolean }): Promise<{ page: BookPageItem }> {
  return apiAdmin("/api/admin/pages", { pageId, action: "ocr", ...payload }, "PATCH");
}

/** Public page list for the source viewer (no admin key; text included, paginated). */
export async function fetchBookPages(slug: string, opts?: { volume?: number; take?: number; skip?: number }): Promise<{ pages: BookPageItem[]; total: number; volumes: number[] }> {
  const sp = new URLSearchParams({ slug });
  if (opts?.volume !== undefined) sp.set("volume", String(opts.volume));
  if (opts?.take !== undefined) sp.set("take", String(opts.take));
  if (opts?.skip) sp.set("skip", String(opts.skip));
  return apiGet(`/api/books/pages?${sp.toString()}`);
}

export async function triggerReindex(bookId: string): Promise<{ book: { slug: string }; pagesConsidered: number; docs: number }> {
  return apiAdmin("/api/admin/reindex", { bookId }, "POST");
}

export interface ImportResult {
  duplicate: boolean;
  book: { id: string; slug: string; titleEn: string };
  sourceRef?: string;
  checksum?: string;
}

/**
 * Multipart PDF upload with progress (fetch has no upload-progress events,
 * so XMLHttpRequest is used here — same admin key, same error envelope).
 */
export function uploadPdf(
  file: File,
  fields: Record<string, string>,
  onProgress: (loaded: number, total: number) => void,
): Promise<ImportResult> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", "/api/admin/import");
    xhr.setRequestHeader("x-admin-key", ADMIN_KEY);
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) onProgress(e.loaded, e.total);
    };
    xhr.onload = () => {
      let json: ImportResult & { error?: string } = {} as ImportResult;
      try { json = JSON.parse(xhr.responseText); } catch { /* fall through */ }
      if (xhr.status === 201 || (xhr.status === 409 && (json as ImportResult).duplicate)) {
        resolve(json as ImportResult);
      } else {
        reject(new Error((json as { error?: string }).error || `Upload failed: ${xhr.status}`));
      }
    };
    xhr.onerror = () => reject(new Error("Network disconnected during upload."));
    xhr.ontimeout = () => reject(new Error("Upload timed out."));
    const fd = new FormData();
    fd.append("pdf", file, file.name);
    for (const [k, v] of Object.entries(fields)) {
      if (v !== "") fd.append(k, v);
    }
    xhr.send(fd);
  });
}
