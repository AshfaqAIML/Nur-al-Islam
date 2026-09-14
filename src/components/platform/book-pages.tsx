"use client";

import { useCallback, useEffect, useState } from "react";
import { BookOpenText, ChevronLeft, ChevronRight, FileSearch, ImageIcon } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { usePlatform, useT } from "@/lib/store";
import { useToast } from "@/hooks/use-toast";
import { cn } from "@/lib/utils";
import { ManuscriptPanel, EmptyState } from "@/components/platform/architectural";
import { VerificationBadge } from "@/components/platform/badges";
import { ShareBar } from "@/components/platform/share-bar";
import {
  BookPageItem, buildBookPageParam, fetchBookPages, formatJild,
} from "@/lib/book-api";
import { PageStatusBadge } from "@/components/platform/book-processing";

const PAGE_TAKE = 20;

/** Page list + reader for one book. Paginated — never loads whole books. */
export function BookPages({ slug, initialPage }: { slug: string; initialPage?: number | null }) {
  const t = useT();
  const { toast } = useToast();
  const { setView } = usePlatform();
  const [volume, setVolume] = useState<string>("all");
  const [volumes, setVolumes] = useState<number[]>([]);
  const [pages, setPages] = useState<BookPageItem[] | null>(null);
  const [total, setTotal] = useState(0);
  const [skip, setSkip] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<BookPageItem | null>(null);

  const load = useCallback(async (vol: string, off: number) => {
    setError(null);
    try {
      const d = await fetchBookPages(slug, {
        volume: vol === "all" ? undefined : Number(vol),
        take: PAGE_TAKE,
        skip: off,
      });
      setPages(d.pages);
      setTotal(d.total);
      setVolumes(d.volumes);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load pages");
      setPages([]);
    }
  }, [slug]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      if (cancelled) return;
      setPages(null); setSkip(0); setSelected(null);
      await load("all", 0);
    })().catch(() => {});
    return () => { cancelled = true; };
  }, [slug, load]);

  // Deep-linked page: book/{slug}/{page} — fetch it directly (volume unknown).
  useEffect(() => {
    if (!initialPage || !pages) return;
    let cancelled = false;
    (async () => {
      const hit = pages.find((p) => p.pageNumber === initialPage);
      if (cancelled) return;
      if (hit) { setSelected(hit); return; }
      // Not on this slice: locate via unfiltered scan in volume order.
      try {
        const d = await fetchBookPages(slug, { take: 500 });
        if (cancelled) return;
        const found = d.pages.find((p) => p.pageNumber === initialPage) ?? null;
        if (found) {
          if (found.volume !== undefined) setVolume(String(found.volume));
          setSelected(found);
        } else {
          toast({ title: t("bpPageMissing") ?? `Page ${initialPage} not found in this book`, variant: "destructive" });
        }
      } catch { /* list error already surfaced */ }
    })().catch(() => {});
    return () => { cancelled = true; };
  }, [initialPage, pages, slug, t, toast]);

  const changeVolume = (v: string) => {
    setVolume(v); setSkip(0); setSelected(null);
    void load(v, 0);
  };
  const changeSkip = (off: number) => {
    setSkip(off); setSelected(null);
    void load(volume, off);
  };
  const openPage = (p: BookPageItem) => {
    setSelected(p);
    setView("sources", buildBookPageParam(slug, p.pageNumber));
  };

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <Select value={volume} onValueChange={changeVolume}>
          <SelectTrigger className="h-8 w-40 text-xs"><SelectValue placeholder={t("bpAllVolumes") ?? "All volumes"} /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">{t("bpAllVolumes") ?? "All volumes"}</SelectItem>
            {volumes.map((v) => (
              <SelectItem key={v} value={String(v)}>{formatJild(v, "en")} · vol. {v}</SelectItem>
            ))}
          </SelectContent>
        </Select>
        <span className="text-[11px] tabular-nums text-muted-foreground">
          {total > 0 ? `${skip + 1}–${Math.min(skip + PAGE_TAKE, total)} / ${total}` : ""}
        </span>
        <span className="ms-auto flex gap-1">
          <Button size="sm" variant="outline" className="h-7 w-7 p-0" disabled={skip === 0} onClick={() => changeSkip(Math.max(0, skip - PAGE_TAKE))} aria-label="Previous pages">
            <ChevronLeft className="h-3.5 w-3.5 rtl:rotate-180" />
          </Button>
          <Button size="sm" variant="outline" className="h-7 w-7 p-0" disabled={skip + PAGE_TAKE >= total} onClick={() => changeSkip(skip + PAGE_TAKE)} aria-label="Next pages">
            <ChevronRight className="h-3.5 w-3.5 rtl:rotate-180" />
          </Button>
        </span>
      </div>

      {error && (
        <div className="rounded-lg border border-rose-300 p-3 text-xs dark:border-rose-900">
          <p className="font-medium text-rose-800 dark:text-rose-300">{error}</p>
          <Button size="sm" variant="outline" className="mt-2" onClick={() => load(volume, skip)}>{t("retry") ?? "Retry"}</Button>
        </div>
      )}
      {pages === null && !error && <div className="space-y-2">{[...Array(3)].map((_, i) => <Skeleton key={i} className="h-14 rounded-lg" />)}</div>}
      {pages !== null && pages.length === 0 && !error && (
        <EmptyState title={t("bpNoPages") ?? "No processed pages yet"} hint={t("bpNoPagesHint") ?? "Pages appear here once the book is processed (Admin → Book processing)."} />
      )}

      <ul className="max-h-56 space-y-1.5 overflow-y-auto pe-1">
        {(pages ?? []).map((p) => (
          <li key={p.id}>
            <button
              onClick={() => openPage(p)}
              aria-current={selected?.id === p.id}
              className={cn(
                "flex w-full items-center gap-2 rounded-lg border px-3 py-2 text-start transition-colors hover:border-emerald-300 dark:hover:border-emerald-800",
                selected?.id === p.id && "border-emerald-400 bg-emerald-50/50 dark:border-emerald-700 dark:bg-emerald-950/30"
              )}
            >
              <BookOpenText className="h-3.5 w-3.5 shrink-0 text-muted-foreground" aria-hidden />
              <span className="text-xs font-semibold tabular-nums">{formatJild(p.volume, "en")} · p. {p.pageNumber}</span>
              {p.chapter && <span className="max-w-full truncate text-[11px] text-muted-foreground">{p.chapter}</span>}
              <span className="ms-auto flex shrink-0 items-center gap-1.5">
                {p.verified
                  ? <Badge variant="outline" className="border-emerald-300 text-[10px] text-emerald-800 dark:border-emerald-700 dark:text-emerald-300">✓ {t("verified")}</Badge>
                  : <PageStatusBadge status={p.status} />}
              </span>
            </button>
          </li>
        ))}
      </ul>

      {selected && <PageReader page={selected} slug={slug} />}
    </div>
  );
}

/** Single processed page: image (if stored) + text states with verification labels. */
export function PageReader({ page, slug }: { page: BookPageItem; slug: string }) {
  const t = useT();
  const display = page.verifiedText ?? page.ocrText ?? "";
  return (
    <ManuscriptPanel>
      <div className="space-y-3 p-4">
        <div className="flex flex-wrap items-center gap-2">
          <h4 className="font-scholarly text-sm font-bold" dir="auto">
            {formatJild(page.volume, "en")} · p. {page.pageNumber}
          </h4>
          {page.chapter && <span className="max-w-full truncate text-xs text-muted-foreground" dir="auto">{page.chapter}</span>}
          <span className="ms-auto flex items-center gap-1.5">
            {page.verified
              ? <VerificationBadge status="VERIFIED" />
              : <VerificationBadge status="UNVERIFIED" />}
            <PageStatusBadge status={page.status} />
          </span>
        </div>

        <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-[11px] text-muted-foreground sm:grid-cols-4">
          <div><dt className="inline font-medium">{t("bpConfidence") ?? "Confidence"}: </dt><dd className="inline tabular-nums">{page.ocrConfidence !== null && page.ocrConfidence !== undefined ? `${Math.round(page.ocrConfidence * 100)}%` : "—"}</dd></div>
          <div><dt className="inline font-medium">{t("bpEngine") ?? "Engine"}: </dt><dd className="inline">{page.engine ?? "—"}</dd></div>
          <div><dt className="inline font-medium">{t("bpLanguage") ?? "Language"}: </dt><dd className="inline">{page.language ?? "—"}</dd></div>
          <div><dt className="inline font-medium">{t("bpAttempts") ?? "Attempts"}: </dt><dd className="inline tabular-nums">{page.attempts}</dd></div>
        </dl>

        {page.imageUrl ? (
          <figure>
            {/* Path for future overlay highlighting: boxes render over this image. */}
            <img src={page.imageUrl} alt={`Page ${page.pageNumber}`} className="max-h-72 w-full rounded-lg border object-contain bg-white" loading="lazy" />
            <figcaption className="mt-1 flex items-center gap-1 text-[10px] text-muted-foreground">
              <ImageIcon className="h-3 w-3" aria-hidden /> {t("bpOriginalImage") ?? "Original page image (preserved)"}
            </figcaption>
          </figure>
        ) : (
          <p className="flex items-center gap-1.5 rounded-lg border border-dashed p-3 text-[11px] text-muted-foreground">
            <FileSearch className="h-3.5 w-3.5 shrink-0" aria-hidden />
            {t("bpNoImage") ?? "No stored page image — text below is the preserved extraction."}
          </p>
        )}

        {page.verifiedText ? (
          <div>
            <h5 className="mb-1 text-[11px] font-bold uppercase tracking-wide text-emerald-800 dark:text-emerald-300">{t("bpVerifiedText") ?? "Verified text"}</h5>
            <p dir="auto" className="font-arabic whitespace-pre-wrap rounded-lg border border-emerald-200 bg-emerald-50/40 p-3 text-sm leading-loose dark:border-emerald-900 dark:bg-emerald-950/20">{page.verifiedText}</p>
          </div>
        ) : null}
        <div>
          <h5 className="mb-1 flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wide text-muted-foreground">
            {t("bpRawOcr") ?? "Raw OCR"} {page.verified ? null : <span className="font-medium normal-case">({t("bpUnverifiedLead") ?? "unverified — retrieval lead only"})</span>}
          </h5>
          <p dir="auto" className="font-arabic max-h-64 overflow-y-auto whitespace-pre-wrap rounded-lg border bg-muted/40 p-3 text-sm leading-loose">
            {page.ocrText || <span className="text-muted-foreground">{t("bpNoText") ?? "No extracted text for this page."}</span>}
          </p>
        </div>

        <div className="flex justify-end border-t pt-2">
          <ShareBar title={`${formatJild(page.volume, "en")} · p. ${page.pageNumber}`} section={slug} pathOverride={`sources/${buildBookPageParam(slug, page.pageNumber)}`} compact />
        </div>
      </div>
    </ManuscriptPanel>
  );
}
