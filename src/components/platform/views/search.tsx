"use client";

import { useCallback, useEffect, useState } from "react";
import { Search, Sparkles } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { usePlatform, useT } from "@/lib/store";
import { useLoc } from "@/lib/use-loc";
import { apiGet, SearchHit } from "@/lib/api";
import { SOURCE_TYPE_META } from "@/lib/ai.client";
import { EmptyState, ManuscriptPanel, BookSpine } from "@/components/platform/architectural";
import { cn } from "@/lib/utils";

export function SearchView({ param }: { param?: string | null }) {
  const t = useT();
  const { setView } = usePlatform();
  const loc = useLoc();
  const [q, setQ] = useState("");
  const [type, setType] = useState("");
  const [bookId, setBookId] = useState("");
  const [volume, setVolume] = useState("");
  const [bookOptions, setBookOptions] = useState<{ id: string; titleEn: string }[]>([]);
  const [hits, setHits] = useState<SearchHit[] | null>(null);
  const [intent, setIntent] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (param && param !== "focus") {
      try {
        const parsed = JSON.parse(param) as { q?: string; type?: string };
        if (parsed.q) setQ(parsed.q);
        if (parsed.type) setType(parsed.type);
      } catch {
        setQ(param);
      }
    }
  }, [param]);

  const run = useCallback(async () => {
    if (q.trim().length < 2) { setHits(null); return; }
    setLoading(true);
    try {
      const sp = new URLSearchParams({ q: q.trim(), surface: "search" });
      if (type) sp.set("type", type);
      if (bookId) sp.set("bookId", bookId);
      if (volume.trim() !== "") sp.set("volume", volume.trim());
      const data = await apiGet<{ results: SearchHit[]; intent: string | null }>(`/api/search?${sp.toString()}`);
      setHits(data.results);
      setIntent(data.intent);
    } catch { setHits([]); } finally { setLoading(false); }
  }, [q, type, bookId, volume]);

  useEffect(() => {
    const id = setTimeout(run, 250);
    return () => clearTimeout(id);
  }, [run]);

  // Book options for the resource filter (titles only — IDs go to the backend).
  useEffect(() => {
    apiGet<{ books: { id: string; titleEn: string }[] }>("/api/books")
      .then((d) => setBookOptions(d.books.map((b) => ({ id: b.id, titleEn: b.titleEn }))))
      .catch(() => setBookOptions([]));
  }, []);

  function openHit(h: SearchHit) {
    if (h.entityType === "BOOK_PAGE" && h.provenance) {
      // Phase 7: passage → exact book + page in the existing viewer.
      setView("sources", `book/${h.provenance.bookSlug}/${h.provenance.page ?? ""}`.replace(/\/$/, ""));
      return;
    }
    if (h.route.startsWith("misconceptions/")) setView("misconceptions", h.route.split("/")[1]);
    else if (h.route.startsWith("knowledge/")) setView("knowledge", h.route.split("/")[1]);
    else if (h.route.startsWith("bank/")) setView("bank", h.route.split("/")[1]);
    else if (h.route.startsWith("sources/book/")) setView("sources", `book/${h.route.split("/")[2]}`);
    else if (h.route.startsWith("sources/scholar/")) setView("sources", `scholar/${h.route.split("/")[2]}`);
    else if (h.route.startsWith("objections/")) setView("objections", h.route.split("/")[1]);
    else if (h.route === "compare") setView("compare");
    else if (h.route.startsWith("qa/")) setView("qa", h.route.split("/")[1]);
    else if (h.route.startsWith("quran-hadith/")) setView("quran");
    else setView("search", JSON.stringify({ q: h.title }));
  }

  const TYPES = [
    { v: "", label: t("all") }, { v: "TOPIC", label: t("topicsLabel") }, { v: "MISCONCEPTION", label: t("misconceptionsLabel") },
    { v: "OBJECTION", label: t("objectionsLabel") }, { v: "BOOK", label: t("books") }, { v: "SCHOLAR", label: t("scholarsLabel") },
    { v: "HADITH", label: t("hadithCollection") }, { v: "QURAN", label: t("quran") }, { v: "FATWA", label: t("fatwas") },
    { v: "QUESTION", label: t("questions") }, { v: "COMPARISON", label: t("comparisonsLabel") },
    { v: "BOOK_PAGE", label: t("bookPassages") },
  ];

  return (
    <div className="mx-auto max-w-4xl px-4 py-8 sm:px-6">
      {/* Search courtyard — girih-lit focus band */}
      <ManuscriptPanel className="arch-top pattern-girih">
        <div className="px-6 pb-6 pt-9">
          <div className="flex items-center gap-2">
            <Search className="h-6 w-6 text-emerald-700 dark:text-emerald-400" aria-hidden />
            <h1 className="font-scholarly text-3xl font-bold">Global Search</h1>
          </div>
          <p className="mt-2 max-w-2xl text-sm text-muted-foreground">
            Search across questions, answers, books, scholars, hadith, Qur&apos;an, claims, misconceptions, topics — in
            English, Arabic and Urdu (keyword + typo-tolerant matching).
          </p>
          <div className="relative mt-5">
            <Search className="absolute start-4 top-1/2 h-5 w-5 -translate-y-1/2 text-muted-foreground" aria-hidden />
            <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("searchPlaceholder")} className="h-12 rounded-full bg-card/90 ps-11 text-base shadow-subtle" autoFocus />
          </div>
        </div>
      </ManuscriptPanel>

      <div className="mt-4 flex flex-wrap gap-1.5">
        {TYPES.map((tp) => (
          <button
            key={tp.v}
            onClick={() => setType(tp.v)}
            className={cn(
              "rounded-full border px-3 py-1.5 text-xs font-medium transition-colors",
              type === tp.v ? "border-emerald-600 bg-emerald-600 text-white" : "text-muted-foreground hover:bg-accent"
            )}
          >
            {tp.label}
          </button>
        ))}
      </div>

      {/* Resource filters — every control affects the backend request */}
      <div className="mt-3 grid gap-2 sm:grid-cols-2">
        <label className="flex items-center gap-2 text-xs text-muted-foreground">
          <span className="shrink-0">{t("books")}</span>
          <select
            value={bookId}
            onChange={(e) => setBookId(e.target.value)}
            className="h-8 w-full rounded-md border border-input bg-background px-2 text-xs text-foreground"
            aria-label={t("books")}
          >
            <option value="">{t("all")}</option>
            {bookOptions.map((b) => (
              <option key={b.id} value={b.id}>{b.titleEn}</option>
            ))}
          </select>
        </label>
        <label className="flex items-center gap-2 text-xs text-muted-foreground">
          <span className="shrink-0">{t("bpJild") ?? "Jild"}</span>
          <Input
            value={volume}
            onChange={(e) => setVolume(e.target.value.replace(/[^0-9]/g, ""))}
            inputMode="numeric"
            placeholder="4"
            className="h-8 text-xs"
            aria-label={t("bpJild") ?? "Jild"}
          />
        </label>
      </div>

      <div className="mt-6">
        {loading && <div className="space-y-3">{[...Array(4)].map((_, i) => <Skeleton key={i} className="h-20 rounded-xl" />)}</div>}
        {!loading && hits && (
          <>
            <p className="mb-3 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
              <span>{hits.length} {t("searchResults")}</span>
              {intent && (
                <Badge variant="outline" className="gap-1 text-[10px] font-medium">
                  <Sparkles className="h-3 w-3" aria-hidden /> {t(`intent_${intent}`)}
                </Badge>
              )}
              {intent === "misconception" && hits.length > 0 && (
                <span className="text-[10px] italic">{t("searchIntentMisconceptionHint")}</span>
              )}
            </p>
            <div className="space-y-2.5">
              {hits.map((h) => {
                const meta = SOURCE_TYPE_META[h.entityType];
                return (
                  <Card key={`${h.entityType}-${h.entityId}`} className="card-lift relative cursor-pointer overflow-hidden border-border/70" onClick={() => openHit(h)}>
                    <BookSpine />
                    <CardContent className="p-4 ps-5">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <span dir="auto" className="text-sm font-semibold">{loc.title(h.title, h.titleUr, h.titleAr)}</span>
                        <div className="flex items-center gap-1.5">
                          <Badge variant="outline" className="text-[10px]">{meta?.label ?? h.entityType}</Badge>
                          <span className="text-[10px] text-muted-foreground">score {h.score}</span>
                        </div>
                      </div>
                      <p className="mt-1 line-clamp-2 text-xs leading-relaxed text-muted-foreground">{h.snippet}</p>
                      {h.provenance && (
                        <p className="mt-1.5 flex flex-wrap items-center gap-x-1.5 text-[10px] text-muted-foreground" dir="auto">
                          <span className="font-medium text-emerald-700 dark:text-emerald-400">{h.provenance.bookTitle}</span>
                          {h.provenance.author && <span>· {h.provenance.author}</span>}
                          {h.provenance.volume !== null && <span>· vol. {h.provenance.volume}</span>}
                          {h.provenance.page !== null && <span>· p. {h.provenance.page}</span>}
                          {h.provenance.chapter && <span>· {h.provenance.chapter}</span>}
                          {h.provenance.verified && <span className="text-emerald-600">· verified</span>}
                        </p>
                      )}
                    </CardContent>
                  </Card>
                );
              })}
              {hits.length === 0 && (
                <EmptyState
                  title={t("noResults")}
                  hint={t("searchNoResultsHint")}
                >
                  <Button size="sm" variant="outline" onClick={() => setView("ask")}>{t("bankAskInstead")}</Button>
                </EmptyState>
              )}
            </div>
          </>
        )}
        {!loading && !hits && (
          <div className="rounded-xl border border-dashed">
            <EmptyState
              title="Search the whole library"
              hint="Bilingual and typo-tolerant: Arabic, Urdu and English all resolve."
            >
              <p className="text-xs text-muted-foreground">
                Try: <em>tawassul</em> · <em>توسل</em> · <em>raf al-yadayn</em> · <em>mawlid</em> · <em>Ibn Abidin</em> · <em>Fatawa Razvia</em>
              </p>
            </EmptyState>
          </div>
        )}
      </div>
    </div>
  );
}
