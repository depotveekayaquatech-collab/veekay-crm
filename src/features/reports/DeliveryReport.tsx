import { SelectField } from "@/components/ui/Dropdown";
import { useCallback, useState } from "react";
import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { Button } from "@/components/ui/Button";
import { Skeleton } from "@/components/feedback/Skeleton";
import { ErrorState } from "@/components/feedback/ErrorState";
import { IconDownload } from "@/components/ui/icons";
import { usePartners } from "@/features/stores/useStores";
import { SummaryReport } from "@/features/reports/SummaryReport";
import { apiBlob, apiRequest } from "@/services/api";
import { camelize } from "@/lib/camel";
import { daysAgo } from "@/lib/dates";
import { pushToast } from "@/lib/toast";

interface MatrixRow {
  storeId: string;
  name: string;
  externalCode: string;
  platform: string | null;
  state: string | null;
  city: string | null;
  values: Record<string, number>;
  totalBottles: number;
  daysMarked: number;
}
interface Matrix {
  start: string;
  end: string;
  dates: string[];
  total: number;
  page: number;
  pageSize: number;
  storesWithEntries: number;
  grandTotalBottles: number;
  dayTotals: Record<string, number>; // every matching store, not just the rows loaded so far
  rows: MatrixRow[];
}
interface Filters {
  from: string;
  to: string;
  partner: string;
  state: string;
  city: string;
  region: string; // region id
}

const DEFAULTS: Filters = { from: daysAgo(6), to: daysAgo(0), partner: "", state: "", city: "", region: "" };
const PAGE_SIZE = 50; // rows fetched per scroll step
const input =
  "h-10 w-full rounded-lg border border-surface-border bg-surface px-3 text-sm shadow-sm outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20";

function qs(f: Filters, extra: Record<string, string | number> = {}): string {
  const p = new URLSearchParams({ start: f.from, end: f.to, ...Object.fromEntries(Object.entries(extra).map(([k, v]) => [k, String(v)])) });
  if (f.partner) p.set("partner", f.partner);
  if (f.state.trim()) p.set("state", f.state.trim());
  if (f.city.trim()) p.set("city", f.city.trim());
  if (f.region) p.set("region", f.region);
  return p.toString();
}

function Section({ title, subtitle, action, children }: { title: string; subtitle?: string; action?: React.ReactNode; children: React.ReactNode }) {
  return (
    <section className="rounded-xl border border-surface-border bg-surface shadow-card">
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-surface-border/80 px-5 py-4">
        <div>
          <h3 className="text-sm font-bold text-gray-900">{title}</h3>
          {subtitle && <p className="mt-0.5 text-xs text-gray-500">{subtitle}</p>}
        </div>
        {action}
      </header>
      <div className="p-5">{children}</div>
    </section>
  );
}

/* ------------------------------ daily matrix ------------------------------ */

function DailyMatrix() {
  const { data: partners = [] } = usePartners();
  const [draft, setDraft] = useState<Filters>(DEFAULTS);
  const [applied, setApplied] = useState<Filters>(DEFAULTS);
  const [exporting, setExporting] = useState(false);
  const [blankAs, setBlankAs] = useState<"zero" | "blank">("zero");        // an unmarked day in the Excel file: 0 or an empty cell
  const bad = draft.from > draft.to;

  // The regions that have stores of the chosen channel (all regions while no channel is chosen).
  const { data: regions = [] } = useQuery({
    queryKey: ["matrix-regions", draft.partner],
    queryFn: async () => camelize<{ id: string; name: string }[]>(await apiRequest(`/orders/matrix/regions${draft.partner ? `?partner=${draft.partner}` : ""}`)),
    staleTime: 300_000,
  });

  // One endless list: the next batch of stores loads as you scroll to the bottom.
  const query = useInfiniteQuery({
    queryKey: ["order-matrix", applied],
    initialPageParam: 1,
    queryFn: async ({ pageParam }) => camelize<Matrix>(await apiRequest(`/orders/matrix?${qs(applied, { page: pageParam, page_size: PAGE_SIZE })}`)),
    getNextPageParam: (last) => (last.page * last.pageSize < last.total ? last.page + 1 : undefined),
    placeholderData: (prev) => prev,
    refetchOnWindowFocus: false, // every loaded batch would be fetched again
  });
  const { isLoading, isError, refetch, isFetching, isFetchingNextPage, hasNextPage, fetchNextPage } = query;
  const head = query.data?.pages[0];
  const rows = query.data?.pages.flatMap((p) => p.rows) ?? [];
  const data = head ? { ...head, rows } : undefined;

  const onScroll = useCallback(
    (e: React.UIEvent<HTMLDivElement>) => {
      const el = e.currentTarget;
      if (hasNextPage && !isFetchingNextPage && el.scrollHeight - el.scrollTop - el.clientHeight < 600) void fetchNextPage();
    },
    [hasNextPage, isFetchingNextPage, fetchNextPage],
  );

  function generate() {
    if (bad) return;
    setApplied(draft);
  }

  async function exportExcel() {
    setExporting(true);
    try {
      const blob = await apiBlob(`/orders/matrix/export?${qs(applied, { blank_as_zero: blankAs === "zero" ? "true" : "false" })}`);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `daily-distribution-${applied.from}_${applied.to}.xlsx`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      pushToast("Excel downloaded.", "success");
    } finally {
      setExporting(false);
    }
  }

  const dateHead = (iso: string, long: boolean) => {
    const d = new Date(`${iso}T12:00:00`);
    return long
      ? { top: d.toLocaleDateString(undefined, { day: "2-digit", month: "short" }), sub: "" }
      : { top: String(d.getDate()).padStart(2, "0"), sub: d.toLocaleDateString(undefined, { weekday: "short" }) };
  };
  const longRange = (data?.dates.length ?? 0) > 31;

  const dayTotals = data?.dates.map((d) => data.dayTotals[d] ?? 0) ?? [];

  return (
    <div className="flex flex-col gap-6">
      <Section title="Report filters" subtitle="Changing the date range regenerates the daily columns (up to 62 days).">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-6">
          <label className="flex flex-col gap-1.5 text-[13px] font-semibold text-gray-700">
            Date from
            <input type="date" className={input} value={draft.from} max={draft.to} onChange={(e) => setDraft({ ...draft, from: e.target.value })} />
          </label>
          <label className="flex flex-col gap-1.5 text-[13px] font-semibold text-gray-700">
            Date to
            <input type="date" className={input} value={draft.to} min={draft.from} onChange={(e) => setDraft({ ...draft, to: e.target.value })} />
          </label>
          <label className="flex flex-col gap-1.5 text-[13px] font-semibold text-gray-700">
            Channel
            <SelectField className={input} value={draft.partner} onChange={(e) => setDraft({ ...draft, partner: e.target.value, region: "" })}>
              <option value="">All channels</option>
              {partners.map((p) => (
                <option key={p.slug} value={p.slug}>{p.name}</option>
              ))}
            </SelectField>
          </label>
          <label className="flex flex-col gap-1.5 text-[13px] font-semibold text-gray-700">
            Region
            <SelectField className={input} value={draft.region} onChange={(e) => setDraft({ ...draft, region: e.target.value })}>
              <option value="">All regions</option>
              {regions.map((r) => (
                <option key={r.id} value={r.id}>{r.name}</option>
              ))}
            </SelectField>
          </label>
          <label className="flex flex-col gap-1.5 text-[13px] font-semibold text-gray-700">
            State
            <input className={input} value={draft.state} onChange={(e) => setDraft({ ...draft, state: e.target.value })} placeholder="All states" />
          </label>
          <label className="flex flex-col gap-1.5 text-[13px] font-semibold text-gray-700">
            City
            <input className={input} value={draft.city} onChange={(e) => setDraft({ ...draft, city: e.target.value })} placeholder="All cities" />
          </label>
        </div>
        {bad && <p className="mt-2 text-sm text-status-danger">“Date from” must not be after “Date to”.</p>}
        <div className="mt-4 flex gap-2">
          <Button onClick={generate} disabled={bad} isLoading={isFetching && !isLoading}>Generate report</Button>
          <Button
            variant="secondary"
            onClick={() => {
              setDraft(DEFAULTS);
              setApplied(DEFAULTS);
            }}
          >
            Reset
          </Button>
        </div>
      </Section>

      <Section
        title="Daily delivery matrix"
        subtitle={data ? `${data.total} stores · ${data.grandTotalBottles.toLocaleString()} bottles · ${data.storesWithEntries} with deliveries` : undefined}
        action={
          <div className="flex flex-wrap items-center gap-3">
            <label className="flex items-center gap-2 text-xs font-semibold text-gray-600">
              Days nobody marked
              <SelectField className="h-9 rounded-lg border border-surface-border bg-surface px-2 text-sm" value={blankAs} onChange={(e) => setBlankAs(e.target.value as "zero" | "blank")} aria-label="Unmarked days in the Excel file">
                <option value="zero">Show as 0</option>
                <option value="blank">Leave blank</option>
              </SelectField>
            </label>
            <Button variant="secondary" size="sm" onClick={() => void exportExcel()} isLoading={exporting} disabled={!data?.total}>
              <IconDownload className="h-3.5 w-3.5" />
              Export Excel
            </Button>
          </div>
        }
      >
        {isLoading && <Skeleton className="h-64" />}
        {isError && <ErrorState message="Couldn't load the matrix." onRetry={() => refetch()} />}
        {data && data.rows.length === 0 && (
          <div className="py-12 text-center">
            <p className="text-sm font-bold text-gray-800">No stores match</p>
            <p className="mt-1 text-sm text-gray-500">Change the channel, region, state or city and generate again.</p>
          </div>
        )}
        {data && data.rows.length > 0 && (
          <>
            <div onScroll={onScroll} className="max-h-[70vh] overflow-auto rounded-lg border border-surface-border">
              <table className="min-w-full border-separate border-spacing-0 text-sm">
                <thead>
                  <tr>
                    <th className="sticky left-0 top-0 z-30 w-10 border-b border-surface-border bg-ink-800 px-2 py-2.5 text-center text-[11px] font-bold text-white/70">#</th>
                    <th className="sticky left-10 top-0 z-30 min-w-[15rem] border-b border-r border-surface-border bg-ink-800 px-3 py-2.5 text-left text-[11px] font-bold text-white/70">Store</th>
                    <th className="sticky top-0 z-20 border-b border-surface-border bg-ink-800 px-3 py-2.5 text-left text-[11px] font-bold text-white/70">Channel</th>
                    <th className="sticky top-0 z-20 border-b border-surface-border bg-ink-800 px-3 py-2.5 text-left text-[11px] font-bold text-white/70">State / City</th>
                    {data.dates.map((d) => {
                      const h = dateHead(d, longRange);
                      return (
                        <th key={d} title={d} className="sticky top-0 z-20 min-w-[2.6rem] border-b border-surface-border bg-ink-800 px-1.5 py-1.5 text-center">
                          <div className="text-[11px] font-bold text-white">{h.top}</div>
                          {h.sub && <div className="text-[9px] font-medium text-white/50">{h.sub}</div>}
                        </th>
                      );
                    })}
                    <th className="sticky top-0 z-20 border-b border-surface-border bg-ink-700 px-3 py-2.5 text-right text-[11px] font-bold text-white">Total</th>
                  </tr>
                </thead>
                <tbody>
                  {data.rows.map((r, i) => (
                    <tr key={r.storeId} className="group">
                      <td className="sticky left-0 z-10 border-b border-surface-border/70 bg-surface px-2 py-2 text-center text-xs text-gray-400 group-hover:bg-surface-subtle">{i + 1}</td>
                      <td className="sticky left-10 z-10 border-b border-r border-surface-border/70 bg-surface px-3 py-2 group-hover:bg-surface-subtle">
                        <div className="max-w-[15rem] truncate font-medium text-gray-900" title={r.name}>{r.name}</div>
                        <div className="text-[11px] text-gray-500">{r.externalCode}</div>
                      </td>
                      <td className="border-b border-surface-border/70 px-3 py-2 text-xs text-gray-600 group-hover:bg-surface-subtle">{r.platform ?? "—"}</td>
                      <td className="whitespace-nowrap border-b border-surface-border/70 px-3 py-2 text-xs text-gray-600 group-hover:bg-surface-subtle">{[r.state, r.city].filter(Boolean).join(" · ") || "—"}</td>
                      {data.dates.map((d) => {
                        const v = r.values[d];
                        return (
                          <td
                            key={d}
                            className={`border-b border-surface-border/70 px-1.5 py-2 text-center tabular-nums group-hover:bg-surface-subtle ${
                              v === undefined ? "text-gray-300" : v === 0 ? "text-gray-400" : "font-semibold text-gray-900"
                            }`}
                          >
                            {v === undefined ? "·" : v}
                          </td>
                        );
                      })}
                      <td className="border-b border-surface-border/70 bg-surface-subtle px-3 py-2 text-right font-bold tabular-nums text-heading">{r.totalBottles.toLocaleString()}</td>
                    </tr>
                  ))}
                  <tr>
                    <td colSpan={4} className="sticky bottom-0 left-0 z-20 border-t border-surface-border bg-surface-muted px-3 py-2.5 text-xs font-bold text-gray-600">
                      Total · all {data.total} stores
                    </td>
                    {dayTotals.map((t, i) => (
                      <td key={data.dates[i]} className="sticky bottom-0 z-10 border-t border-surface-border bg-surface-muted px-1.5 py-2.5 text-center text-xs font-bold tabular-nums text-gray-700">{t || ""}</td>
                    ))}
                    <td className="sticky bottom-0 z-10 border-t border-surface-border bg-surface-muted px-3 py-2.5 text-right text-xs font-bold tabular-nums text-heading">
                      {data.grandTotalBottles.toLocaleString()}
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
            <p className="mt-2 text-xs text-gray-400">
              · = nothing marked · 0 = marked with zero bottles ·{" "}
              {isFetchingNextPage ? "Loading more stores…" : hasNextPage ? `Showing ${data.rows.length} of ${data.total} stores — scroll for more` : `All ${data.total} stores shown`}
            </p>
          </>
        )}
      </Section>
    </div>
  );
}

/* ---------------------------------- shell --------------------------------- */

export function DeliveryReport() {
  const [view, setView] = useState<"matrix" | "summary">("matrix");
  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-[11px] font-bold text-status-success">Delivery reports</p>
          <h2 className="mt-1 text-2xl font-bold text-heading">{view === "matrix" ? "Daily distribution report" : "Delivery summary"}</h2>
          <p className="mt-1 text-sm text-gray-500">
            {view === "matrix"
              ? "One store per row with delivered bottle counts for every selected day."
              : "Bottle volumes for a period, grouped by region, channel, state or store."}
          </p>
        </div>
        <div className="flex gap-1 rounded-lg bg-surface-muted p-1">
          {([["matrix", "Daily matrix"], ["summary", "Summary"]] as const).map(([id, label]) => (
            <button
              key={id}
              onClick={() => setView(id)}
              className={`rounded-md px-3.5 py-1.5 text-sm font-medium transition-[color,background-color,border-color,box-shadow,opacity,transform] ${view === id ? "bg-surface text-brand-700 shadow-sm" : "text-gray-500 hover:text-gray-800"}`}
            >
              {label}
            </button>
          ))}
        </div>
      </div>
      {view === "matrix" ? <DailyMatrix /> : <SummaryReport />}
    </div>
  );
}
