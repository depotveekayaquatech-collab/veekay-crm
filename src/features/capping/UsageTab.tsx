import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { SelectField } from "@/components/ui/Dropdown";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/feedback/EmptyState";
import { ErrorState } from "@/components/feedback/ErrorState";
import { Skeleton } from "@/components/feedback/Skeleton";
import { IconSearch } from "@/components/ui/icons";
import { copyText } from "@/lib/clipboard";
import { pushToast } from "@/lib/toast";
import { formatLimitReport, groupByVendor } from "@/lib/zeptoLimitReport";
import { dateLabel } from "@/features/capping/helpers";
import { field } from "@/features/capping/styles";
import { getCappingUsage, type CapLevel, type UsageRow } from "@/services/capping";

const LEVEL: Record<CapLevel, { label: string; tone: "danger" | "warning" | "success" | "neutral" }> = {
  OVER: { label: "Over cap", tone: "danger" },
  AHEAD: { label: "Ahead of pace", tone: "warning" },
  NEAR: { label: "Near cap", tone: "warning" },
  OK: { label: "OK", tone: "success" },
  NO_CAP: { label: "No cap", tone: "neutral" },
};
type Filter = "ALL" | CapLevel | "ATTENTION";
type Sort = "level" | "percent" | "used" | "name";
const PAGE = 100;
const n = (v: number | null) => (v === null ? "—" : v.toLocaleString("en-IN"));

function Stat({ label, value, tone, active, onClick }: { label: string; value: number; tone: string; active: boolean; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={`flex flex-col gap-1 rounded-xl border bg-surface p-4 text-left shadow-card transition-colors hover:border-brand-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 ${active ? "border-brand-500 ring-1 ring-brand-500" : "border-surface-border"}`}
    >
      <span className="text-[11px] font-bold text-gray-500">{label}</span>
      <span className={`text-2xl font-extrabold tabular-nums ${tone}`}>{value.toLocaleString("en-IN")}</span>
    </button>
  );
}

function UsageBar({ row }: { row: UsageRow }) {
  if (row.percent === null) return <span className="text-gray-400">—</span>;
  const w = Math.min(100, row.percent);
  const color = row.alert === "OVER" ? "bg-status-danger" : row.alert === "NEAR" || row.alert === "AHEAD" ? "bg-status-warning" : "bg-status-success";
  return (
    <div className="flex w-full min-w-[84px] items-center gap-2">
      <div className="h-2 flex-1 overflow-hidden rounded-full bg-surface-border" role="progressbar" aria-valuenow={Math.round(row.percent)} aria-valuemin={0} aria-valuemax={100}>
        <div className={`h-full ${color}`} style={{ width: `${w}%` }} />
      </div>
      <span className="w-12 text-right text-xs font-semibold tabular-nums">{row.percent}%</span>
    </div>
  );
}

/** The Zepto vendor message for the stores shown: per vendor, each store's monthly limit, what was supplied so far and the pending limit. Copy it, or preview it first. */
function PasteText({ rows, monthLabel, current }: { rows: UsageRow[]; monthLabel: string; current: boolean }) {
  const [show, setShow] = useState(false);
  const text = useMemo(() => {
    const asOn = current ? ` (as on ${new Date().toLocaleDateString("en-IN", { day: "numeric", month: "short" })})` : "";
    const stores = rows.map((r) => ({ vendor_name: r.vendorName, store_name: r.outletName, external_code: r.outletId, monthly_limit: r.monthlyCap, bottles: r.used, pending: r.remaining, over_by: r.excess }));
    return formatLimitReport(`Zepto - Vendor limit, ${monthLabel}${asOn}`, groupByVendor(stores));
  }, [rows, monthLabel, current]);

  async function copy() {
    const ok = await copyText(text);
    pushToast(ok ? `Copied for ${rows.length} store${rows.length === 1 ? "" : "s"}. Paste it where you need it.` : "Couldn't copy. Open the preview and copy it by hand.", ok ? "success" : "error");
  }

  return (
    <div className="rounded-xl border border-surface-border bg-surface-subtle/60 p-3">
      <p className="text-xs font-bold text-gray-500">Text to paste</p>
      <p className="mt-1 text-xs text-gray-500">Vendor by vendor: monthly limit (capping × 30), supplied till date and the pending limit, for the stores listed below.</p>
      <div className="mt-2 flex flex-wrap items-center gap-2">
        <Button size="sm" onClick={() => void copy()} disabled={!rows.length}>Copy text</Button>
        <button type="button" className="text-xs font-semibold text-brand-600 hover:text-brand-700" onClick={() => setShow((v) => !v)} aria-expanded={show}>
          {show ? "Hide preview" : "Preview"}
        </button>
      </div>
      {show && rows.length > 0 && <textarea readOnly value={text} rows={Math.min(14, text.split("\n").length + 1)} className="mt-2 w-full resize-y rounded-lg border border-surface-border bg-surface p-3 font-mono text-xs" aria-label="Text preview" />}
    </div>
  );
}

/**
 * Usage against the limit, for analysis: every live Zepto store with its daily capping, monthly limit (x 30), the bottles marked so far this month (every entry,
 * whoever entered it), what is left, the percentage and the status (over, ahead of pace, near, OK, no capping). Click a count to filter by it.
 */
export function UsageTab({ onUpdate }: { onUpdate: (storeId: string) => void }) {
  const [month, setMonth] = useState("");
  const [q, setQ] = useState("");
  const [filter, setFilter] = useState<Filter>("ALL");
  const [state, setState] = useState("");
  const [city, setCity] = useState("");
  const [sort, setSort] = useState<Sort>("level");
  const [limit, setLimit] = useState({ n: PAGE, sig: "" });

  // never show the previous month's rows as if they were the chosen month's
  const { data, isLoading, isError, error, refetch } = useQuery({ queryKey: ["capping", "usage", month], queryFn: () => getCappingUsage(month || undefined), staleTime: 30_000, placeholderData: undefined });
  const rows = useMemo(() => data?.rows ?? [], [data]);
  const states = useMemo(() => [...new Set(rows.map((r) => r.state).filter(Boolean) as string[])].sort(), [rows]);
  const cities = useMemo(() => [...new Set(rows.filter((r) => !state || r.state === state).map((r) => r.city).filter(Boolean) as string[])].sort(), [rows, state]);

  const shown = useMemo(() => {
    const needle = q.trim().toLowerCase();
    const out = rows.filter(
      (r) =>
        (filter === "ALL" || (filter === "ATTENTION" ? r.alert === "OVER" || r.alert === "AHEAD" || r.alert === "NEAR" : r.alert === filter)) &&
        (!state || r.state === state) &&
        (!city || r.city === city) &&
        (!needle || r.outletName.toLowerCase().includes(needle) || r.outletId.toLowerCase().includes(needle)),
    );
    if (sort === "percent") out.sort((a, b) => (b.percent ?? -1) - (a.percent ?? -1));
    else if (sort === "used") out.sort((a, b) => b.used - a.used);
    else if (sort === "name") out.sort((a, b) => a.outletName.localeCompare(b.outletName));
    return out;
  }, [rows, q, filter, state, city, sort]);

  const sig = `${month}|${q}|${filter}|${state}|${city}|${sort}`;
  const visible = limit.sig === sig ? limit.n : PAGE;   // back to the first page whenever the view changes
  const s = data?.summary;
  const toggle = (f: Filter) => setFilter((cur) => (cur === f ? "ALL" : f));

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-xs text-gray-500">
          {data ? `${data.monthLabel} · monthly limit = daily capping × 30 · every entry of the month is counted${s ? ` · ${s.entries.toLocaleString("en-IN")} entries, ${s.bottles.toLocaleString("en-IN")} bottles` : ""}` : "Bottles used against each store's monthly limit."}
        </p>
        <SelectField className="h-10 rounded-lg border border-surface-border bg-surface px-3 text-sm shadow-sm" value={month || data?.month || ""} onChange={(e) => setMonth(e.target.value)} aria-label="Month">
          {(data?.months ?? [data?.month ?? ""]).filter(Boolean).map((m) => (
            <option key={m} value={m}>{new Date(`${m}-01T12:00:00`).toLocaleDateString("en-IN", { month: "long", year: "numeric" })}</option>
          ))}
        </SelectField>
      </div>

      {isLoading && <Skeleton className="h-64" />}
      {isError && <ErrorState message={error instanceof Error ? error.message : "Couldn't load the capping usage."} onRetry={() => refetch()} />}

      {data && s && (
        <>
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
            <Stat label="Over cap" value={s.over} tone="text-status-danger" active={filter === "OVER"} onClick={() => toggle("OVER")} />
            <Stat label="Ahead of pace" value={s.ahead} tone="text-status-warning" active={filter === "AHEAD"} onClick={() => toggle("AHEAD")} />
            <Stat label={`Near cap (${data.warnPercent}%+)`} value={s.near} tone="text-status-warning" active={filter === "NEAR"} onClick={() => toggle("NEAR")} />
            <Stat label="Within limit" value={s.ok} tone="text-status-success" active={filter === "OK"} onClick={() => toggle("OK")} />
            <Stat label="No cap set" value={s.noCap} tone="text-gray-700" active={filter === "NO_CAP"} onClick={() => toggle("NO_CAP")} />
          </div>

          <section className="rounded-xl border border-surface-border bg-surface p-4 shadow-card">
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
              <label className="relative sm:col-span-2">
                <IconSearch className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" />
                <input className={`${field} pl-9`} value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search store name or Outlet ID" aria-label="Search stores" />
              </label>
              <SelectField className={field} value={state} onChange={(e) => { setState(e.target.value); setCity(""); }} aria-label="State">
                <option value="">All states</option>
                {states.map((x) => <option key={x} value={x}>{x}</option>)}
              </SelectField>
              <SelectField className={field} value={city} onChange={(e) => setCity(e.target.value)} aria-label="City">
                <option value="">All cities</option>
                {cities.map((x) => <option key={x} value={x}>{x}</option>)}
              </SelectField>
              <SelectField className={field} value={sort} onChange={(e) => setSort(e.target.value as Sort)} aria-label="Sort">
                <option value="level">Sort: alert level</option>
                <option value="percent">Sort: highest usage %</option>
                <option value="used">Sort: most bottles used</option>
                <option value="name">Sort: store name</option>
              </SelectField>
            </div>
            <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-gray-500">
              <button type="button" className={`rounded-lg px-3 py-1.5 text-sm font-medium ${filter === "ATTENTION" ? "bg-brand-500 text-white" : "bg-surface-subtle text-gray-700 hover:bg-surface-border/60"}`} onClick={() => toggle("ATTENTION")}>
                Only over / ahead / near cap
              </button>
              {(filter !== "ALL" || q || state || city) && (
                <button type="button" className="font-semibold text-brand-600 hover:text-brand-700" onClick={() => { setFilter("ALL"); setQ(""); setState(""); setCity(""); }}>
                  Clear filters
                </button>
              )}
              <span className="ml-auto">{shown.length} of {rows.length} stores</span>
            </div>
          </section>

          <PasteText rows={shown} monthLabel={data.monthLabel} current={data.month === data.months[0]} />

          {shown.length === 0 ? (
            <EmptyState title="No stores match" description={rows.length ? "Change the search or filters." : "There are no live Zepto stores yet."} />
          ) : (
            <div className="stacked-table overflow-x-auto rounded-xl border border-surface-border bg-surface shadow-card">
              <table className="w-full min-w-[1100px] border-collapse text-sm">
                <thead>
                  <tr className="bg-surface-subtle/80 text-left text-[11px] font-bold text-gray-500">
                    {["Store", "State / City", "Daily cap", "Monthly limit", "Used", "Left", "Usage", "Status", "Entries", "Highest day", "Last entry", "Owner", ""].map((h, i) => (
                      <th key={i} className="border-b border-surface-border px-3 py-3 first:pl-4">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {shown.slice(0, visible).map((r) => (
                    <tr key={r.storeId} className="border-b border-surface-border/60 hover:bg-surface-subtle/50">
                      <td data-label="Store" className="max-w-[260px] px-3 py-3 pl-4">
                        <p className="break-words font-semibold text-gray-900">{r.outletName}</p>
                        <p className="break-all text-xs text-gray-500">{r.outletId}</p>
                      </td>
                      <td data-label="State / City" className="px-3 py-3 text-gray-600">{[r.city, r.state].filter(Boolean).join(", ") || "—"}</td>
                      <td data-label="Daily cap" className="px-3 py-3 tabular-nums">{n(r.dailyCap)}</td>
                      <td data-label="Monthly limit" className="px-3 py-3 tabular-nums">{n(r.monthlyCap)}</td>
                      <td data-label="Used" className="px-3 py-3 font-semibold tabular-nums">{n(r.used)}</td>
                      <td data-label="Left" className="px-3 py-3 tabular-nums">
                        {r.alert === "OVER" ? <span className="font-semibold text-status-danger">+{n(r.excess)} over</span> : n(r.remaining)}
                        {r.alert === "AHEAD" && <p className="text-xs font-semibold text-status-warning">{n(r.aheadBy)} ahead of today&apos;s {n(r.allowedToDate)}</p>}
                      </td>
                      <td data-label="Usage" className="px-3 py-3"><UsageBar row={r} /></td>
                      <td data-label="Status" className="px-3 py-3"><Badge tone={LEVEL[r.alert].tone}>{LEVEL[r.alert].label}</Badge></td>
                      <td data-label="Entries" className="px-3 py-3 tabular-nums">{n(r.entries)}</td>
                      <td data-label="Highest day" className="px-3 py-3 tabular-nums">{r.entries ? n(r.highestDay) : "—"}</td>
                      <td data-label="Last entry" className="px-3 py-3 tabular-nums text-gray-600">{r.lastEntry ? dateLabel(r.lastEntry) : "—"}</td>
                      <td data-label="Owner" className="px-3 py-3 text-gray-600">{r.ownerName ?? "—"}</td>
                      <td data-label="" className="px-3 py-3 text-right">
                        <Button size="sm" variant="secondary" onClick={() => onUpdate(r.storeId)} aria-label={`Update capping for ${r.outletName}`}>Update</Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {shown.length > visible && (
            <div className="flex justify-center">
              <Button variant="secondary" onClick={() => setLimit({ n: visible + PAGE, sig })}>
                Show {Math.min(PAGE, shown.length - visible)} more ({shown.length - visible} left)
              </Button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
