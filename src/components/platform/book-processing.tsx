"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertTriangle, CheckCircle2, ChevronRight, Clock3, FileSearch, LibraryBig,
  Loader2, Play, RefreshCw, RotateCcw, Square, Upload, XCircle,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { usePlatform, useT } from "@/lib/store";
import { Book, apiGet } from "@/lib/api";
import { useToast } from "@/hooks/use-toast";
import { cn } from "@/lib/utils";
import {
  JOB_STATUS_META, PAGE_STATUS_META, BookPageItem, ProcessingJob,
  createProcessingJob, fetchJobStatus, fetchPageDetail, fetchPages, fetchProcessingJobs,
  formatJild, isTerminalJob, jobProgress, pageReviewedFrom, pageReviewReasons,
  patchPage, patchProcessingJob, triggerReindex, uploadPdf,
} from "@/lib/book-api";

function StatusBadge({ status, meta }: { status: string; meta: Record<string, { tone: string }> }) {
  const tone = meta[status]?.tone ?? "stone";
  const tones: Record<string, string> = {
    emerald: "border-emerald-300 text-emerald-800 dark:border-emerald-700 dark:text-emerald-300",
    amber: "border-amber-300 text-amber-800 dark:border-amber-700 dark:text-amber-300",
    rose: "border-rose-300 text-rose-800 dark:border-rose-700 dark:text-rose-300",
    sky: "border-sky-300 text-sky-800 dark:border-sky-700 dark:text-sky-300",
    stone: "text-muted-foreground",
  };
  return <Badge variant="outline" className={cn("text-[10px]", tones[tone])}>{status.replaceAll("_", " ")}</Badge>;
}

export function JobStatusBadge({ status }: { status: string }) {
  return <StatusBadge status={status} meta={JOB_STATUS_META} />;
}

export function PageStatusBadge({ status }: { status: string }) {
  return <StatusBadge status={status} meta={PAGE_STATUS_META} />;
}

function fmtDate(v: string | null) {
  if (!v) return "—";
  try { return new Date(v).toLocaleString(); } catch { return "—"; }
}

const POLL_MS = 5000;

export function BookProcessing() {
  const t = useT();
  const { toast } = useToast();
  const { setView } = usePlatform();
  const [books, setBooks] = useState<Book[] | null>(null);
  const [bookId, setBookId] = useState("");
  const [jobs, setJobs] = useState<ProcessingJob[] | null>(null);
  const [jobsError, setJobsError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [review, setReview] = useState<BookPageItem[] | null>(null);
  const [failed, setFailed] = useState<BookPageItem[] | null>(null);
  const [editing, setEditing] = useState<BookPageItem | null>(null);
  const [verifiedText, setVerifiedText] = useState("");
  // create-job form
  const [volume, setVolume] = useState("1");
  const [totalPages, setTotalPages] = useState("");
  const [sourceRef, setSourceRef] = useState("");
  // upload form (Phase 8: real PDF import, multipart + progress)
  const [upFile, setUpFile] = useState<File | null>(null);
  const [upTitle, setUpTitle] = useState("");
  const [upLang, setUpLang] = useState("");
  const [upVolumes, setUpVolumes] = useState("1");
  const [upLoaded, setUpLoaded] = useState(0);
  const [upTotal, setUpTotal] = useState(0);
  const [uploading, setUploading] = useState(false);

  const book = useMemo(() => (books ?? []).find((b) => b.id === bookId) ?? null, [books, bookId]);

  useEffect(() => {
    apiGet<{ books: Book[] }>("/api/books").then((d) => setBooks(d.books)).catch(() => setBooks([]));
  }, []);

  const loadJobs = useCallback(async (silent = false) => {
    if (!bookId) { setJobs(null); return; }
    if (!silent) setJobsError(null);
    try {
      const d = await fetchProcessingJobs(bookId);
      setJobs(d.jobs ?? []);
    } catch (e) {
      if (!silent) setJobsError(e instanceof Error ? e.message : "Failed to load jobs");
      setJobs([]);
    }
  }, [bookId]);

  const loadQueues = useCallback(async () => {
    if (!bookId) { setReview(null); setFailed(null); return; }
    try {
      const [r, f] = await Promise.all([
        fetchPages({ bookId, reviewOnly: true, take: 50 }),
        fetchPages({ bookId, take: 100 }),
      ]);
      setReview(r.pages);
      setFailed(f.pages.filter((p) => p.status === "FAILED"));
    } catch {
      setReview([]); setFailed([]);
    }
  }, [bookId]);

  useEffect(() => {
    setJobs(null); setReview(null); setFailed(null);
    if (bookId) { void loadJobs(); void loadQueues(); }
  }, [bookId, loadJobs, loadQueues]);

  // Real-time: no job SSE endpoint exists, so poll while work is active;
  // refetch on tab-visible recovers after disconnect (backend authoritative).
  const active = (jobs ?? []).some((j) => !isTerminalJob(j.status));
  useEffect(() => {
    if (!active) return;
    const id = setInterval(() => { void loadJobs(true); void loadQueues(); }, POLL_MS);
    const onVis = () => { if (document.visibilityState === "visible") { void loadJobs(true); void loadQueues(); } };
    document.addEventListener("visibilitychange", onVis);
    return () => { clearInterval(id); document.removeEventListener("visibilitychange", onVis); };
  }, [active, loadJobs, loadQueues]);

  const submitJob = async () => {
    if (!bookId) return;
    const total = totalPages.trim() === "" ? 0 : Number(totalPages);
    if (totalPages.trim() !== "" && (!Number.isInteger(total) || total < 0 || total > 10000)) {
      toast({ title: t("bpInvalidTotal") ?? "Total pages must be 0–10000", variant: "destructive" });
      return;
    }
    setCreating(true);
    try {
      const meta: Record<string, unknown> = {};
      if (sourceRef.trim()) meta.sourceRef = sourceRef.trim();
      await createProcessingJob({ bookId, totalPages: total, volume: Number(volume) || 1, metadata: meta });
      toast({ title: t("bpJobCreated") ?? "Processing job created — watching progress" });
      setTotalPages(""); setSourceRef("");
      await loadJobs(); await loadQueues();
    } catch (e) {
      toast({ title: e instanceof Error ? e.message : t("error"), variant: "destructive" });
    } finally {
      setCreating(false);
    }
  };

  const act = async (job: ProcessingJob, action: "cancel" | "retry") => {
    setBusy(job.id + action);
    try {
      await patchProcessingJob(job.id, action);
      toast({ title: action === "cancel" ? (t("bpCancelled") ?? "Job cancelled") : (t("bpRetrying") ?? "Job re-queued — failed pages resume") });
      await loadJobs(); await loadQueues();
    } catch (e) {
      toast({ title: e instanceof Error ? e.message : t("error"), variant: "destructive" });
    } finally {
      setBusy(null);
    }
  };

  const reindex = async (job: ProcessingJob) => {
    setBusy(job.id + "reindex");
    try {
      const r = await triggerReindex(job.bookId);
      toast({ title: `${t("bpIndexed") ?? "Indexed"}: ${r.docs} / ${r.pagesConsidered}` });
    } catch (e) {
      toast({ title: e instanceof Error ? e.message : t("error"), variant: "destructive" });
    } finally {
      setBusy(null);
    }
  };

  const openReview = (p: BookPageItem) => {
    setEditing(p);
    setVerifiedText(p.verifiedText ?? "");
    // Full text states arrive on demand (list responses stay lean).
    fetchPageDetail(p.id)
      .then((d) => {
        setEditing(d.page);
        setVerifiedText((v) => (v === "" ? (d.page.verifiedText ?? "") : v));
      })
      .catch(() => {});
  };

  /** Rough word-overlap similarity for the reviewer (NOT an accuracy score). */
  const similarityNote = (a: string | null | undefined, b: string | null | undefined): string | null => {
    if (!a?.trim() || !b?.trim()) return null;
    const sa = new Set(a.split(/\s+/));
    const sb = new Set(b.split(/\s+/));
    let inter = 0;
    for (const w of sa) if (sb.has(w)) inter++;
    const pct = Math.round((2 * inter) / (sa.size + sb.size) * 100);
    return `${pct}% word overlap`;
  };

  const saveVerified = async () => {
    if (!editing) return;
    setBusy(editing.id + "verify");
    try {
      await patchPage(editing.id, "verify", { verifiedText: verifiedText || undefined });
      toast({ title: t("bpVerifiedSaved") ?? "Verified text saved — raw OCR preserved" });
      setEditing(null);
      await loadQueues(); await loadJobs(true);
    } catch (e) {
      toast({ title: e instanceof Error ? e.message : t("error"), variant: "destructive" });
    } finally {
      setBusy(null);
    }
  };

  const pageAct = async (p: BookPageItem, action: "requeue" | "fail") => {
    setBusy(p.id + action);
    try {
      await patchPage(p.id, action);
      toast({ title: action === "requeue" ? (t("bpRequeued") ?? "Page re-queued") : (t("bpMarkedFailed") ?? "Page marked failed") });
      await loadQueues(); await loadJobs(true);
    } catch (e) {
      toast({ title: e instanceof Error ? e.message : t("error"), variant: "destructive" });
    } finally {
      setBusy(null);
    }
  };

  return (
    <section aria-label="Book processing">
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wider text-muted-foreground">
        {t("bpTitle") ?? "Book processing"}
      </h2>
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2 text-base">
            <LibraryBig className="h-4 w-4 text-emerald-700 dark:text-emerald-400" aria-hidden />
            {t("bpTitle") ?? "Book processing"}
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-5">
          {/* Book selector */}
          <div className="grid gap-3 sm:grid-cols-[1fr_auto]">
            <div>
              <label className="text-xs font-medium text-muted-foreground" htmlFor="bp-book">
                {t("bpSelectBook") ?? "Book"}
              </label>
              <Select value={bookId} onValueChange={setBookId}>
                <SelectTrigger id="bp-book" className="mt-1"><SelectValue placeholder={t("bpSelectBook") ?? "Select a book"} /></SelectTrigger>
                <SelectContent>
                  {(books ?? []).map((b) => (
                    <SelectItem key={b.id} value={b.id}>{b.titleEn} · {b.ocrStatus}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="flex items-end gap-2">
              <Button variant="outline" size="sm" onClick={() => { void loadJobs(); void loadQueues(); }} disabled={!bookId} className="gap-1.5">
                <RefreshCw className="h-3.5 w-3.5" /> {t("refresh")}
              </Button>
              {book && (
                <Button variant="outline" size="sm" onClick={() => setView("sources", `book/${book.slug}`)} className="gap-1.5">
                  {t("bpOpenViewer") ?? "Open viewer"} <ChevronRight className="h-3.5 w-3.5 rtl:rotate-180" />
                </Button>
              )}
            </div>
          </div>

          {!bookId && (
            <p className="rounded-lg border border-dashed p-4 text-center text-xs text-muted-foreground">
              {t("bpPickBook") ?? "Select a book to manage its processing jobs, review queue, and indexing."}
            </p>
          )}

          {/* Import: real PDF upload (multipart, progress) → Book + sourceRef */}
          <div className="rounded-lg border p-4">
            <h3 className="flex items-center gap-1.5 text-sm font-semibold">
              <Upload className="h-3.5 w-3.5 text-emerald-700 dark:text-emerald-400" aria-hidden />
              {t("bpImport") ?? "Import PDF"}
            </h3>
            <p className="mt-1 text-[11px] leading-relaxed text-muted-foreground">
              {t("bpImportHint") ?? "Upload stores the original server-side and creates the Book. Processing starts separately below — upload does not imply processed."}
            </p>
            <div className="mt-3 grid gap-2 sm:grid-cols-2">
              <div className="sm:col-span-2">
                <label className="text-[11px] text-muted-foreground" htmlFor="bp-file">{t("bpPdfFile") ?? "PDF file"}</label>
                <Input
                  id="bp-file" type="file" accept="application/pdf,.pdf" className="mt-1 h-9 text-xs"
                  onChange={(e) => { setUpFile(e.target.files?.[0] ?? null); setUpLoaded(0); setUpTotal(0); }}
                />
              </div>
              <div>
                <label className="text-[11px] text-muted-foreground" htmlFor="bp-title">{t("bpBookTitle") ?? "Book title"} *</label>
                <Input id="bp-title" value={upTitle} onChange={(e) => setUpTitle(e.target.value)} className="mt-1 h-8" maxLength={300} />
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="text-[11px] text-muted-foreground" htmlFor="bp-lang">{t("bpLanguage") ?? "Language"}</label>
                  <Input id="bp-lang" value={upLang} onChange={(e) => setUpLang(e.target.value)} placeholder="Urdu" className="mt-1 h-8" maxLength={60} />
                </div>
                <div>
                  <label className="text-[11px] text-muted-foreground" htmlFor="bp-vols">{t("bpVolumesCount") ?? "Volumes"}</label>
                  <Input id="bp-vols" inputMode="numeric" value={upVolumes} onChange={(e) => setUpVolumes(e.target.value)} className="mt-1 h-8" />
                </div>
              </div>
            </div>
            {uploading && (
              <div className="mt-3">
                <div className="h-2 overflow-hidden rounded-full bg-muted" role="progressbar" aria-valuenow={upTotal ? Math.round((upLoaded / upTotal) * 100) : 0} aria-valuemin={0} aria-valuemax={100} aria-label={t("bpUploading") ?? "Uploading"}>
                  <div className="h-full rounded-full bg-sky-600 transition-all" style={{ width: upTotal ? `${Math.round((upLoaded / upTotal) * 100)}%` : "0%" }} />
                </div>
                <p className="mt-1 text-[11px] tabular-nums text-muted-foreground">
                  {(upLoaded / 1048576).toFixed(1)} / {(upTotal / 1048576).toFixed(1)} MB
                  {upTotal ? ` (${Math.round((upLoaded / upTotal) * 100)}%)` : ""}
                </p>
              </div>
            )}
            <Button
              size="sm" className="mt-3 gap-1.5 bg-emerald-700 text-white hover:bg-emerald-800"
              disabled={uploading || !upFile || !upTitle.trim()}
              onClick={async () => {
                if (!upFile) return;
                setUploading(true); setUpLoaded(0); setUpTotal(upFile.size);
                try {
                  const r = await uploadPdf(upFile, { title: upTitle.trim(), language: upLang.trim(), volumes: upVolumes.trim() },
                    (loaded, total) => { setUpLoaded(loaded); setUpTotal(total); });
                  if (r.duplicate) {
                    toast({ title: t("bpDuplicate") ?? "Duplicate source — existing book kept", description: r.book.titleEn });
                  } else {
                    toast({ title: t("bpImported") ?? "PDF imported — original stored", description: r.book.titleEn });
                  }
                  setUpFile(null); setUpTitle(""); setUpLang(""); setUpVolumes("1");
                  const refreshed = await apiGet<{ books: Book[] }>("/api/books").catch(() => null);
                  if (refreshed) {
                    setBooks(refreshed.books);
                    setBookId(r.book.id);
                  }
                } catch (e) {
                  toast({ title: e instanceof Error ? e.message : t("error"), variant: "destructive" });
                } finally {
                  setUploading(false);
                }
              }}
            >
              {uploading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Upload className="h-3.5 w-3.5" />}
              {t("bpUpload") ?? "Upload PDF"}
            </Button>
          </div>

          {bookId && (
            <>
              {/* Create job */}
              <div className="rounded-lg border p-4">
                <h3 className="flex items-center gap-1.5 text-sm font-semibold">
                  <Play className="h-3.5 w-3.5 text-emerald-700 dark:text-emerald-400" aria-hidden />
                  {t("bpNewJob") ?? "Start processing"}
                </h3>
                <p className="mt-1 text-[11px] leading-relaxed text-muted-foreground">
                  {t("bpNewJobHint") ?? "Originals live in storage/ and are never modified. totalPages creates resumable page stubs; sourceRef records the original file."}
                </p>
                <div className="mt-3 grid gap-2 sm:grid-cols-4">
                  <div>
                    <label className="text-[11px] text-muted-foreground" htmlFor="bp-vol">{t("bpVolume") ?? "Volume"}</label>
                    <Input id="bp-vol" inputMode="numeric" value={volume} onChange={(e) => setVolume(e.target.value)} className="mt-1 h-8" />
                  </div>
                  <div>
                    <label className="text-[11px] text-muted-foreground" htmlFor="bp-total">{t("bpTotalPages") ?? "Total pages"}</label>
                    <Input id="bp-total" inputMode="numeric" value={totalPages} onChange={(e) => setTotalPages(e.target.value)} placeholder="0" className="mt-1 h-8" />
                  </div>
                  <div className="sm:col-span-2">
                    <label className="text-[11px] text-muted-foreground" htmlFor="bp-src">{t("bpSourceRef") ?? "Source ref (storage path)"}</label>
                    <Input id="bp-src" value={sourceRef} onChange={(e) => setSourceRef(e.target.value)} placeholder="storage/originals/book.pdf" className="mt-1 h-8" dir="ltr" />
                  </div>
                </div>
                <Button size="sm" className="mt-3 gap-1.5 bg-emerald-700 text-white hover:bg-emerald-800" disabled={creating} onClick={submitJob}>
                  {creating ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Play className="h-3.5 w-3.5" />}
                  {t("bpStart") ?? "Create job"}
                </Button>
              </div>

              {/* Jobs */}
              <div>
                <h3 className="mb-2 text-sm font-semibold">{t("bpJobs") ?? "Processing jobs"}</h3>
                {jobs === null && <div className="space-y-2">{[...Array(2)].map((_, i) => <Skeleton key={i} className="h-24 rounded-lg" />)}</div>}
                {jobsError && (
                  <div className="rounded-lg border border-rose-300 p-3 text-xs dark:border-rose-900">
                    <p className="flex items-center gap-1.5 font-medium text-rose-800 dark:text-rose-300"><AlertTriangle className="h-3.5 w-3.5" />{jobsError}</p>
                    <Button size="sm" variant="outline" className="mt-2" onClick={() => loadJobs()}>{t("retry") ?? "Retry"}</Button>
                  </div>
                )}
                {jobs !== null && jobs.length === 0 && !jobsError && (
                  <p className="rounded-lg border border-dashed p-4 text-center text-xs text-muted-foreground">{t("bpNoJobs") ?? "No processing jobs yet."}</p>
                )}
                <div className="space-y-2.5">
                  {(jobs ?? []).map((j) => {
                    const pct = jobProgress(j);
                    const terminal = isTerminalJob(j.status);
                    return (
                      <div key={j.id} className="rounded-lg border p-3.5">
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <div className="flex items-center gap-2">
                            <JobStatusBadge status={j.status} />
                            <span className="text-[11px] text-muted-foreground">{t("bpStage") ?? "Stage"}: {j.stage}</span>
                            {active && !terminal && <Loader2 className="h-3.5 w-3.5 animate-spin text-sky-600" aria-label="processing" />}
                          </div>
                          <span className="text-xs font-bold tabular-nums">{pct}%</span>
                        </div>
                        <div className="mt-2 h-2 overflow-hidden rounded-full bg-muted" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100} aria-label={`Job progress ${pct}%`}>
                          <div className="h-full rounded-full bg-emerald-600 transition-all" style={{ width: `${pct}%` }} />
                        </div>
                        <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[11px] tabular-nums text-muted-foreground">
                          <span>{t("bpTotalPages") ?? "Total"}: {j.totalPages}</span>
                          <span className="text-emerald-700 dark:text-emerald-400">{t("bpDone") ?? "Done"}: {j.processedPages}</span>
                          <span className="text-rose-700 dark:text-rose-400">{t("bpFailed") ?? "Failed"}: {j.failedPages}</span>
                          <span className="text-amber-700 dark:text-amber-400">{t("bpReview") ?? "Review"}: {j.reviewPages}</span>
                        </div>
                        <div className="mt-1.5 grid gap-0.5 text-[11px] text-muted-foreground sm:grid-cols-3">
                          <span className="inline-flex items-center gap-1"><Clock3 className="h-3 w-3" />{t("bpStarted") ?? "Started"}: {fmtDate(j.startedAt)}</span>
                          <span>{t("bpUpdated") ?? "Updated"}: {fmtDate(j.updatedAt)}</span>
                          <span>{t("bpCompleted") ?? "Completed"}: {fmtDate(j.completedAt)}</span>
                        </div>
                        {j.error && <p className="mt-1.5 rounded bg-rose-50 px-2 py-1 text-[11px] text-rose-900 dark:bg-rose-950/50 dark:text-rose-200">{j.error}</p>}
                        <div className="mt-2.5 flex flex-wrap gap-1.5">
                          {!terminal && (
                            <Button size="sm" variant="outline" className="h-7 gap-1 px-2 text-[11px]" disabled={busy === j.id + "cancel"} onClick={() => act(j, "cancel")}>
                              <Square className="h-3 w-3" /> {t("bpCancel") ?? "Cancel"}
                            </Button>
                          )}
                          {(j.status === "FAILED" || j.status === "REQUIRES_REVIEW" || j.status === "COMPLETED_WITH_WARNINGS") && (
                            <Button size="sm" variant="outline" className="h-7 gap-1 px-2 text-[11px]" disabled={busy === j.id + "retry"} onClick={() => act(j, "retry")}>
                              <RotateCcw className="h-3 w-3" /> {t("bpRetryJob") ?? "Retry failed"}
                            </Button>
                          )}
                          <Button size="sm" variant="outline" className="h-7 gap-1 px-2 text-[11px]" disabled={busy === j.id + "reindex"} onClick={() => reindex(j)}>
                            <FileSearch className="h-3 w-3" /> {t("bpReindex") ?? "Index pages"}
                          </Button>
                          <Button size="sm" variant="ghost" className="h-7 gap-1 px-2 text-[11px]" onClick={() => fetchJobStatus(j.id).then(() => { void loadJobs(true); }).catch(() => {})}>
                            <RefreshCw className="h-3 w-3" /> {t("bpCheckStatus") ?? "Check status"}
                          </Button>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>

              {/* Review queue */}
              <div>
                <h3 className="mb-2 flex items-center gap-1.5 text-sm font-semibold">
                  <FileSearch className="h-3.5 w-3.5 text-amber-700 dark:text-amber-400" aria-hidden />
                  {t("bpReviewQueue") ?? "Pages needing review"} {(review?.length ?? 0) > 0 && (
                    <Badge variant="outline" className="tabular-nums">{review!.length}</Badge>
                  )}
                </h3>
                {review === null && <Skeleton className="h-16 rounded-lg" />}
                {review !== null && review.length === 0 && (
                  <p className="rounded-lg border border-dashed p-4 text-center text-xs text-muted-foreground">
                    <CheckCircle2 className="mx-auto mb-1 h-4 w-4 text-emerald-600" aria-hidden />
                    {t("bpReviewEmpty") ?? "No pages awaiting review."}
                  </p>
                )}
                <div className="space-y-2">
                  {(review ?? []).map((p) => (
                    <button key={p.id} onClick={() => openReview(p)} className="w-full rounded-lg border p-3 text-start transition-colors hover:border-amber-300 dark:hover:border-amber-800">
                      <div className="flex flex-wrap items-center gap-2">
                        <PageStatusBadge status={p.status} />
                        <span className="text-xs font-semibold tabular-nums">{formatJild(p.volume, "en")} · p. {p.pageNumber}</span>
                        {p.chapter && <span className="max-w-full truncate text-[11px] text-muted-foreground">{p.chapter}</span>}
                        <span className="ms-auto text-[11px] tabular-nums text-muted-foreground">
                          {p.ocrConfidence !== null && p.ocrConfidence !== undefined ? `${Math.round(p.ocrConfidence * 100)}%` : "—"} · {p.engine ?? "—"}
                        </span>
                      </div>
                      {p.error && <p className="mt-1 line-clamp-1 text-[11px] text-rose-700 dark:text-rose-400">{p.error}</p>}
                    </button>
                  ))}
                </div>
              </div>

              {/* Failed pages */}
              {(failed ?? []).length > 0 && (
                <div>
                  <h3 className="mb-2 flex items-center gap-1.5 text-sm font-semibold text-rose-800 dark:text-rose-300">
                    <XCircle className="h-3.5 w-3.5" aria-hidden />
                    {t("bpFailedPages") ?? "Failed pages"} <Badge variant="outline" className="tabular-nums">{failed!.length}</Badge>
                  </h3>
                  <div className="space-y-2">
                    {failed!.map((p) => (
                      <div key={p.id} className="flex flex-wrap items-center gap-2 rounded-lg border p-3">
                        <PageStatusBadge status={p.status} />
                        <span className="text-xs font-semibold tabular-nums">{formatJild(p.volume, "en")} · p. {p.pageNumber}</span>
                        <span className="ms-auto" />
                        <Button size="sm" variant="outline" className="h-7 gap-1 px-2 text-[11px]" disabled={busy === p.id + "requeue"} onClick={() => pageAct(p, "requeue")}>
                          <RotateCcw className="h-3 w-3" /> {t("bpRequeue") ?? "Requeue"}
                        </Button>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </>
          )}
        </CardContent>
      </Card>

      {/* Review editor dialog */}
      <Dialog open={!!editing} onOpenChange={(o) => !o && setEditing(null)}>
        <DialogContent className="max-h-[88vh] overflow-y-auto sm:max-w-2xl">
          {editing && (
            <>
              <DialogHeader className="text-start">
                <DialogTitle className="flex flex-wrap items-center gap-2 text-base">
                  {t("bpReviewPage") ?? "Review page"} · {formatJild(editing.volume, "en")} · p. {editing.pageNumber}
                  <PageStatusBadge status={editing.status} />
                </DialogTitle>
                <DialogDescription>
                  {editing.chapter ?? ""} · {editing.engine ?? "—"}
                  {editing.ocrConfidence !== null && editing.ocrConfidence !== undefined ? ` · ${Math.round(editing.ocrConfidence * 100)}%` : ""}
                  {editing.error ? ` · ${t("bpReason") ?? "Reason"}: ${editing.error}` : ""}
                </DialogDescription>
                {pageReviewReasons(editing.signals).length > 0 && (
                  <div className="rounded-lg border border-amber-200 bg-amber-50/60 px-3 py-2 dark:border-amber-900 dark:bg-amber-950/30" role="note" aria-label={t("bpWhyReview") ?? "Why this page needs review"}>
                    <p className="text-[11px] font-semibold text-amber-900 dark:text-amber-300">{t("bpWhyReview") ?? "Why review"}:</p>
                    <ul className="mt-0.5 list-inside list-disc text-[11px] text-amber-900/90 dark:text-amber-200/90">
                      {pageReviewReasons(editing.signals).map((r) => <li key={r}>{r}</li>)}
                    </ul>
                  </div>
                )}
                {editing.verified && pageReviewedFrom(editing.signals) && (
                  <p className="text-[11px] text-muted-foreground">
                    {t("bpVerifiedFrom") ?? "Verified from"}: {pageReviewedFrom(editing.signals)}
                  </p>
                )}
              </DialogHeader>
              <div className="grid gap-3 md:grid-cols-2">
                <div>
                  <h4 className="mb-1 text-xs font-bold uppercase tracking-wide text-muted-foreground">{t("bpRawOcr") ?? "Raw OCR (never edited)"}</h4>
                  <p dir="auto" className="font-arabic max-h-56 overflow-y-auto whitespace-pre-wrap rounded-lg border bg-muted/40 p-3 text-sm leading-loose">{editing.ocrText || "—"}</p>
                  {editing.normalizedText && (
                    <>
                      <h4 className="mb-1 mt-3 text-xs font-bold uppercase tracking-wide text-muted-foreground">{t("bpNormalized") ?? "Normalized (search index)"}</h4>
                      <p dir="auto" className="font-arabic max-h-32 overflow-y-auto whitespace-pre-wrap rounded-lg border bg-muted/40 p-3 text-xs leading-loose">{editing.normalizedText}</p>
                    </>
                  )}
                  {/* Phase 13: secondary capture side-by-side (review aid only). */}
                  {editing.ocrTextSecondary ? (
                    <div className="mt-3 rounded-lg border border-sky-200 bg-sky-50/40 p-3 dark:border-sky-900 dark:bg-sky-950/20">
                      <h4 className="flex flex-wrap items-center gap-1.5 text-xs font-bold uppercase tracking-wide text-sky-800 dark:text-sky-300">
                        {t("bpSecondaryOcr") ?? "Secondary OCR"}
                        <span className="font-medium normal-case tabular-nums text-muted-foreground">
                          {editing.engineSecondary ?? ""}{editing.ocrConfidenceSecondary !== null && editing.ocrConfidenceSecondary !== undefined ? ` · ${Math.round(editing.ocrConfidenceSecondary * 100)}%` : ""}
                        </span>
                      </h4>
                      {similarityNote(editing.ocrText, editing.ocrTextSecondary) && (
                        <p className="mt-1 text-[11px] text-muted-foreground">
                          {t("bpSimilarity") ?? "Rough word overlap with primary"}: {similarityNote(editing.ocrText, editing.ocrTextSecondary)} ({t("bpSimilarityNote") ?? "similarity only — not accuracy"})
                        </p>
                      )}
                      <p dir="auto" className="font-arabic mt-1.5 max-h-40 overflow-y-auto whitespace-pre-wrap rounded-lg border bg-card p-2.5 text-xs leading-loose">{editing.ocrTextSecondary}</p>
                      <Button
                        size="sm" variant="outline" className="mt-2 h-7 gap-1 px-2 text-[11px]"
                        onClick={() => setVerifiedText(editing.ocrTextSecondary ?? "")}
                      >
                        {t("bpUseSecondary") ?? "Use as verified base (still requires Save)"}
                      </Button>
                    </div>
                  ) : (
                    <div className="mt-3 flex flex-wrap items-center gap-2 rounded-lg border border-dashed p-3">
                      <p className="text-[11px] text-muted-foreground">{t("bpNoSecondary") ?? "No secondary capture for this page."}</p>
                      <Button
                        size="sm" variant="ghost" className="h-7 gap-1 px-2 text-[11px]"
                        disabled={busy === editing.id + "retry2"}
                        onClick={async () => {
                          setBusy(editing.id + "retry2");
                          try {
                            await patchPage(editing.id, "retry-secondary");
                            toast({ title: t("bpSecondaryQueued") ?? "Secondary capture re-queued" });
                          } catch (e) {
                            toast({ title: e instanceof Error ? e.message : t("error"), variant: "destructive" });
                          } finally {
                            setBusy(null);
                          }
                        }}
                      >
                        <RotateCcw className="h-3 w-3" /> {t("bpRetrySecondary") ?? "Capture secondary"}
                      </Button>
                    </div>
                  )}
                </div>
                <div>
                  <label htmlFor="bp-verified" className="mb-1 block text-xs font-bold uppercase tracking-wide text-emerald-800 dark:text-emerald-300">
                    {t("bpVerifiedText") ?? "Verified text (editable)"}
                  </label>
                  <Textarea id="bp-verified" dir="auto" value={verifiedText} onChange={(e) => setVerifiedText(e.target.value)} rows={10} className="font-arabic resize-y leading-loose" placeholder={editing.ocrText ?? ""} />
                  <p className="mt-1 text-[11px] text-muted-foreground">{t("bpVerifiedHint") ?? "Saving writes verified text only — raw OCR is preserved."}</p>
                </div>
              </div>
              <DialogFooter className="gap-2">
                <Button variant="outline" size="sm" disabled={busy === editing.id + "requeue"} onClick={() => { void pageAct(editing, "requeue").then(() => setEditing(null)); }}>
                  <RotateCcw className="h-3.5 w-3.5" /> {t("bpRequeue") ?? "Requeue"}
                </Button>
                <Button size="sm" className="gap-1.5 bg-emerald-700 text-white hover:bg-emerald-800" disabled={busy === editing.id + "verify"} onClick={saveVerified}>
                  {busy === editing.id + "verify" ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <CheckCircle2 className="h-3.5 w-3.5" />}
                  {t("bpSaveVerified") ?? "Save verified"}
                </Button>
              </DialogFooter>
            </>
          )}
        </DialogContent>
      </Dialog>
    </section>
  );
}

