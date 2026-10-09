/**
 * Deeper admin-dashboard insights. All numbers come from the existing
 * /orders/report + /orders/pending + /orders/insights endpoints — nothing
 * here is computed from made-up data.
 */
import { useMemo, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { Badge } from "@/components/ui/Badge";
import { Skeleton } from "@/components/feedback/Skeleton";
import { Select } from "@/components/ui/Select";
import { AreaChart, BarList, DonutChart } from "@/features/dashboard/charts";
import { IconAlertTriangle, IconCheckCircle } from "@/components/ui/icons";
import { daysAgo } from "@/lib/dates";
import { distinctOptions } from "@/lib/options";
import { usePending, useReport } from "@/services/reports";
import { useTestReports } from "@/features/reports/testReports";
import type { DashboardInsights } from "@/types/order";

/* ---------------------------- shared bits --------------------------- */

function Panel({ title, subtitle, action, children, className = "" }: { title: string; subtitle?: string; action?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={`rounded-xl border border-surface-border bg-surface shadow-card ${className}`}>
      <header className="flex items-center justify-between gap-3 border-b border-surface-border/80 px-5 py-4">
        <div className="min-w-0">
          <h3 className="text-sm font-bold text-gray-900">{title}</h3>
          {subtitle && <p className="mt-0.5 text-xs text-gray-500">{subtitle}</p>}
        </div>
        {action}
      </header>
      <div className="p-5">{children}</div>
    </section>
  );
}

function PanelLink({ to, children }: { to: string; children: ReactNode }) {
  return (
    <Link to={to} className="text-xs font-medium text-brand-600 hover:text-brand-700">
      {children}
    </Link>
  );
}

function pctChange(cur: number, prev: number): { text: string; tone: "up" | "down" | "flat" } {
  if (prev === 0) return { text: cur > 0 ? "new activity" : "no change", tone: cur > 0 ? "up" : "flat" };
  const p = Math.round(((cur - prev) / prev) * 100);
  if (p === 0) return { text: "flat vs prior period", tone: "flat" };
  return { text: `${p > 0 ? "▲" : "▼"} ${Math.abs(p)}% vs prior period`, tone: p > 0 ? "up" : "down" };
}

const toneText = { up: "text-status-success", down: "text-status-danger", flat: "text-gray-500" };

function sum(a: number[]): number {
  return a.reduce((s, x) => s + x, 0);
}

/* ------------------------- data hook (shared) ----------------------- */

function useInsightData() {
  const end = daysAgo(0);
  // r60 is only used for its daily series; r30 for its totals, store count and the top 6 stores — so no full store lists.
  const r60 = useReport(daysAgo(59), end, "partner");
  const r30 = useReport(daysAgo(29), end, "store", { limit: 6 });
  const reg = useReport(daysAgo(29), end, "region");
  const pending = usePending(0, "");
  return { r60, r30, reg, pending };
}

/* --------------------------- alert strip ---------------------------- */

export function AlertStrip({ insights }: { insights?: DashboardInsights }) {
  const { pending } = useInsightData();
  const testReports = useTestReports("zepto");

  const dormantCount = insights?.dormantLive ?? 0;

  const lagging = insights?.platforms.filter((p) => p.totalStores > 0 && p.percent < 50) ?? [];
  const notLive = insights ? insights.storeStatus.PENDING + insights.storeStatus.CLOSE : 0;

  const items: { key: string; tone: "warning" | "danger" | "info"; text: string; to?: string }[] = [];
  if (pending.data && pending.data.pending > 0)
    items.push({ key: "pending", tone: "warning", text: `${pending.data.pending} live store${pending.data.pending > 1 ? "s" : ""} not marked today`, to: "/orders/pending" });
  lagging.forEach((p) =>
    items.push({ key: p.slug, tone: "danger", text: `${p.label} is at ${Math.round(p.percent)}% completion today`, to: "/orders/overview" }),
  );
  if (dormantCount > 0)
    items.push({ key: "dormant", tone: "warning", text: `${dormantCount} live store${dormantCount > 1 ? "s" : ""} with no orders in 30 days`, to: "/stores" });
  if (notLive > 0) items.push({ key: "notlive", tone: "info", text: `${notLive} store${notLive > 1 ? "s" : ""} not live yet`, to: "/stores" });

  const tr = testReports.data;
  if (tr?.platform.enabled && tr.summary.expired > 0)
    items.push({ key: "tr-expired", tone: "danger", text: `${tr.summary.expired} ${tr.platform.name} test report${tr.summary.expired > 1 ? "s have" : " has"} expired`, to: "/reports?tab=test" });
  if (tr?.platform.enabled && tr.summary.expiring > 0)
    items.push({ key: "tr-expiring", tone: "warning", text: `${tr.summary.expiring} ${tr.platform.name} test report${tr.summary.expiring > 1 ? "s" : ""} expiring within ${tr.alertDays} days`, to: "/reports?tab=test" });

  if (!insights || pending.isLoading) return <Skeleton className="h-14" />;

  if (items.length === 0)
    return (
      <div className="flex items-center gap-3 rounded-xl border border-surface-border bg-status-success-soft/60 px-5 py-3.5 text-sm font-medium text-status-success">
        <IconCheckCircle className="h-5 w-5" />
        Everything looks healthy — no alerts right now.
      </div>
    );

  const bg = { warning: "bg-status-warning-soft text-status-warning", danger: "bg-status-danger-soft text-status-danger", info: "bg-status-info-soft text-status-info" };
  return (
    <div className="flex flex-wrap items-center gap-2 rounded-xl border border-surface-border bg-surface px-4 py-3 shadow-card">
      <span className="mr-1 flex items-center gap-1.5 text-xs font-bold uppercase tracking-wider text-gray-500">
        <IconAlertTriangle className="h-4 w-4" /> Needs attention
      </span>
      {items.map((it) => {
        const cls = `rounded-full px-3 py-1 text-xs font-semibold ${bg[it.tone]}`;
        return it.to ? (
          <Link key={it.key} to={it.to} className={`${cls} transition-opacity hover:opacity-80`}>
            {it.text} →
          </Link>
        ) : (
          <span key={it.key} className={cls}>{it.text}</span>
        );
      })}
    </div>
  );
}

/* ---------------------------- KPI row ------------------------------- */

function Kpi({ label, value, hint, hintTone = "flat", loading, tone = "brand" }: { label: string; value: ReactNode; hint?: string; hintTone?: "up" | "down" | "flat"; loading?: boolean; tone?: "brand" | "aqua" | "success" | "warning" }) {
  return (
    <div className={`tile tile-${tone} rounded-xl border border-surface-border bg-surface p-5 shadow-card transition-all duration-200 hover:-translate-y-0.5 hover:shadow-md`}>
      <p className="text-[11px] font-bold uppercase tracking-wider text-gray-500">{label}</p>
      {loading ? (
        <Skeleton className="mt-2 h-8 w-20" />
      ) : (
        <p className="mt-1.5 text-[1.7rem] font-bold leading-none tabular-nums text-heading">{value}</p>
      )}
      {hint && !loading && <p className={`mt-1.5 text-xs font-medium ${toneText[hintTone]}`}>{hint}</p>}
    </div>
  );
}

export function PerformanceKpis({ insights }: { insights?: DashboardInsights }) {
  const { r60, r30 } = useInsightData();
  const loading = r60.isLoading || r30.isLoading;

  const m = useMemo(() => {
    const s = r60.data?.series.map((p) => p.bottles) ?? [];
    if (s.length < 60) return null;
    const last7 = sum(s.slice(-7));
    const prev7 = sum(s.slice(-14, -7));
    const last30 = sum(s.slice(30));
    const prev30 = sum(s.slice(0, 30));
    return { last7, prev7, last30, prev30 };
  }, [r60.data]);

  const live = insights?.storeStatus.LIVE ?? 0;
  const activeStores = r30.data?.rowCount ?? 0;
  const d7 = m ? pctChange(m.last7, m.prev7) : undefined;
  const d30 = m ? pctChange(m.last30, m.prev30) : undefined;
  const avgEntry = r30.data && r30.data.totalEntries ? (r30.data.totalBottles / r30.data.totalEntries).toFixed(1) : "—";

  return (
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
      <Kpi tone="brand" label="Last 7 days" value={m?.last7.toLocaleString() ?? 0} hint={d7?.text} hintTone={d7?.tone} loading={loading} />
      <Kpi tone="aqua" label="Last 30 days" value={m?.last30.toLocaleString() ?? 0} hint={d30?.text} hintTone={d30?.tone} loading={loading} />
      <Kpi tone="success" label="Avg bottles / entry" value={avgEntry} hint={`${r30.data?.avgBottlesPerDay ?? 0} bottles per day (30d)`} loading={loading} />
      <Kpi
        tone="warning"
        label="Active stores (30d)"
        value={`${activeStores} / ${live}`}
        hint={live ? `${Math.round((activeStores / live) * 100)}% of live stores ordering` : undefined}
        hintTone={live && activeStores / live < 0.6 ? "down" : "up"}
        loading={loading || !insights}
      />
    </div>
  );
}

/* ---------------------------- trend card ---------------------------- */

const PRESETS = ["14", "30", "60", "custom"] as const;
type Preset = (typeof PRESETS)[number];
const MAX_CUSTOM_DAYS = 366;

function dayDiff(a: string, b: string): number {
  return Math.round((new Date(`${b}T12:00:00`).getTime() - new Date(`${a}T12:00:00`).getTime()) / 86_400_000);
}

function fmtDay(iso: string): string {
  return new Date(`${iso}T12:00:00`).toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "short", year: "numeric" });
}

function Mini({ label, value, hint }: { label: string; value: ReactNode; hint?: ReactNode }) {
  return (
    <div className="rounded-xl bg-surface-subtle px-3.5 py-2.5">
      <p className="text-[10px] font-bold uppercase tracking-wider text-gray-400">{label}</p>
      <p className="mt-0.5 text-lg font-extrabold tabular-nums text-heading">{value}</p>
      {hint && <p className="text-[11px] text-gray-500">{hint}</p>}
    </div>
  );
}

const FIELD = "h-10 rounded-lg border border-surface-border bg-surface px-3 text-sm shadow-sm outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20";

export function TrendCard({ insights }: { insights?: DashboardInsights }) {
  const today = daysAgo(0);
  const [preset, setPreset] = useState<Preset>("30");
  const [from, setFrom] = useState(daysAgo(29));
  const [to, setTo] = useState(today);
  const [partner, setPartner] = useState("");
  const [region, setRegion] = useState("");
  const [state, setState] = useState("");
  const [picked, setPicked] = useState<string | null>(null);

  const start = preset === "custom" ? from : daysAgo(Number(preset) - 1);
  const end = preset === "custom" ? to : today;
  const rangeError =
    preset !== "custom"
      ? null
      : !from || !to
        ? "Pick both dates."
        : from > to
          ? "The start date is after the end date."
          : dayDiff(from, to) + 1 > MAX_CUSTOM_DAYS
            ? `Pick at most ${MAX_CUSTOM_DAYS} days.`
            : to > today
              ? "Dates can't be in the future."
              : null;
  const filters = { partner, region, state };
  const filtered = Boolean(partner || region || state);

  // One query gives the daily series AND the per-partner split for the whole range.
  const report = useReport(rangeError ? "" : start, rangeError ? "" : end, "partner", filters);
  const series = report.data?.series ?? [];

  // The day being inspected: the picked one if it's inside the range, otherwise the latest day.
  const day = picked && picked >= start && picked <= end ? picked : series.length ? series[series.length - 1].date : "";
  const dayIdx = series.findIndex((p) => p.date === day);
  const dayPoint = dayIdx >= 0 ? series[dayIdx] : null;
  const dayReport = useReport(day, day, "partner", filters);

  const total = report.data?.totalBottles ?? 0;
  const days = report.data?.days ?? series.length;
  const avg = days ? Math.round(total / days) : 0;
  const peak = series.reduce((b, p) => (p.bottles > b.bottles ? p : b), { date: "", label: "—", bottles: 0, entries: 0 });
  const dayRows = dayReport.data?.rows ?? [];
  const vsAvg = dayPoint && avg > 0 ? Math.round(((dayPoint.bottles - avg) / avg) * 100) : null;

  // Region and State only offer what exists for the chosen partner (and State also for the chosen region).
  const partnerOptions = (insights?.platforms ?? []).map((p) => ({ value: p.slug, label: p.label }));
  const ofPartner = useMemo(
    () => (insights?.scopes ?? []).filter((x) => !partner || x.partnerSlug === partner),
    [insights?.scopes, partner],
  );
  const regionOptions = useMemo(
    () => distinctOptions(ofPartner, (x) => (x.region ? { value: x.region, label: x.region } : null)),
    [ofPartner],
  );
  const stateOptions = useMemo(
    () =>
      distinctOptions(
        ofPartner.filter((x) => !region || x.region === region),
        (x) => (x.state ? { value: x.state, label: x.state } : null),
      ),
    [ofPartner, region],
  );

  function choosePreset(p: Preset) {
    if (p === "custom") {
      setFrom(start);
      setTo(end);
    }
    setPreset(p);
  }

  return (
    <Panel
      title="Bottle volume trend"
      subtitle={`${fmtDay(start)} – ${fmtDay(end)}${filtered ? " · filtered" : ""}`}
      action={
        <div className="flex gap-1 rounded-xl bg-surface-muted p-1" role="tablist" aria-label="Date range">
          {PRESETS.map((r) => (
            <button
              key={r}
              role="tab"
              aria-selected={preset === r}
              onClick={() => choosePreset(r)}
              className={`rounded-lg px-2.5 py-1 text-xs font-semibold transition-[color,background-color,box-shadow] ${preset === r ? "bg-surface text-brand-700 shadow-sm" : "text-gray-500 hover:text-gray-800"}`}
            >
              {r === "custom" ? "Custom" : `${r}d`}
            </button>
          ))}
        </div>
      }
    >
      <div className="mb-4 flex flex-wrap items-end gap-2.5">
        {preset === "custom" && (
          <>
            <label className="flex flex-col gap-1 text-[13px] font-semibold text-gray-700">
              From
              <input type="date" value={from} max={to || today} onChange={(e) => setFrom(e.target.value)} className={FIELD} />
            </label>
            <label className="flex flex-col gap-1 text-[13px] font-semibold text-gray-700">
              To
              <input type="date" value={to} min={from} max={today} onChange={(e) => setTo(e.target.value)} className={FIELD} />
            </label>
          </>
        )}
        {partnerOptions.length > 0 && (
          <div className="w-full sm:w-44 [&_label]:sr-only">
            <Select label="Partner" value={partner} onChange={(e) => { setPartner(e.target.value); setRegion(""); setState(""); }} placeholder="All partners" options={partnerOptions} />
          </div>
        )}
        {regionOptions.length > 0 && (
          <div className="w-full sm:w-44 [&_label]:sr-only">
            <Select label="Region" value={region} onChange={(e) => { setRegion(e.target.value); setState(""); }} placeholder="All regions" options={regionOptions} />
          </div>
        )}
        {stateOptions.length > 0 && (
          <div className="w-full sm:w-44 [&_label]:sr-only">
            <Select label="State" value={state} onChange={(e) => setState(e.target.value)} placeholder="All states" options={stateOptions} />
          </div>
        )}
        {filtered && (
          <button
            type="button"
            onClick={() => {
              setPartner("");
              setRegion("");
              setState("");
            }}
            className="h-10 rounded-xl px-3 text-sm font-semibold text-brand-600 hover:bg-brand-50"
          >
            Clear filters
          </button>
        )}
      </div>

      {rangeError && (
        <p role="alert" className="mb-3 rounded-lg bg-status-danger-soft px-3 py-2 text-sm text-status-danger">
          {rangeError}
        </p>
      )}

      {report.isLoading && !report.data ? (
        <Skeleton className="h-64" />
      ) : report.isError ? (
        <p className="rounded-lg bg-status-danger-soft px-3 py-6 text-center text-sm text-status-danger">Could not load this range. Try again.</p>
      ) : (
        <div className={report.isFetching ? "opacity-70 transition-opacity" : "transition-opacity"}>
          <div className="mb-4 grid grid-cols-2 gap-3 lg:grid-cols-4">
            <Mini label="Bottles" value={total.toLocaleString()} hint={`over ${days} day${days === 1 ? "" : "s"}`} />
            <Mini label="Daily average" value={avg.toLocaleString()} hint={`${(report.data?.totalEntries ?? 0).toLocaleString()} entries`} />
            <Mini label="Peak day" value={peak.bottles.toLocaleString()} hint={peak.label} />
            <Mini label="Partners" value={report.data?.rows.length ?? 0} hint={filtered ? "with filters applied" : "with orders in range"} />
          </div>

          {series.length === 0 ? (
            <p className="py-12 text-center text-sm text-gray-500">No data for this range.</p>
          ) : (
            <AreaChart
              data={series.map((p) => ({ label: p.label, value: p.bottles }))}
              valueSuffix=" bottles"
              selected={dayIdx >= 0 ? dayIdx : null}
              onSelect={(i) => setPicked(series[i]?.date ?? null)}
            />
          )}

          {series.length > 0 && (
            <div className="mt-5 rounded-2xl border border-surface-border bg-surface-subtle/60 p-4">
              <div className="flex flex-wrap items-end justify-between gap-3">
                <div>
                  <label htmlFor="trend-day" className="text-[13px] font-semibold text-gray-700">
                    Check a day
                  </label>
                  <div className="mt-1 flex items-center gap-2">
                    <button
                      type="button"
                      aria-label="Previous day"
                      disabled={dayIdx <= 0}
                      onClick={() => setPicked(series[dayIdx - 1]?.date ?? null)}
                      className="h-10 w-9 rounded-lg border border-surface-border bg-surface text-gray-600 hover:text-gray-900 disabled:opacity-40"
                    >
                      ‹
                    </button>
                    <input id="trend-day" type="date" value={day} min={start} max={end} onChange={(e) => e.target.value && setPicked(e.target.value)} className={FIELD} />
                    <button
                      type="button"
                      aria-label="Next day"
                      disabled={dayIdx < 0 || dayIdx >= series.length - 1}
                      onClick={() => setPicked(series[dayIdx + 1]?.date ?? null)}
                      className="h-10 w-9 rounded-lg border border-surface-border bg-surface text-gray-600 hover:text-gray-900 disabled:opacity-40"
                    >
                      ›
                    </button>
                  </div>
                </div>
                <div className="text-right">
                  <p className="text-xs text-gray-500">{day ? fmtDay(day) : ""}</p>
                  <p className="text-3xl font-extrabold tabular-nums text-heading">
                    {(dayPoint?.bottles ?? 0).toLocaleString()}
                    <span className="ml-1.5 text-sm font-semibold text-gray-400">bottles</span>
                  </p>
                  <p className="text-xs text-gray-500">
                    {(dayPoint?.entries ?? 0).toLocaleString()} store entries
                    {vsAvg !== null && (
                      <span className={`ml-2 font-semibold ${vsAvg >= 0 ? "text-status-success" : "text-status-danger"}`}>
                        {vsAvg >= 0 ? "▲" : "▼"} {Math.abs(vsAvg)}% vs average
                      </span>
                    )}
                  </p>
                </div>
              </div>

              {dayRows.length > 0 && (
                <ul className="mt-4 flex flex-wrap gap-2" aria-label="Bottles by partner on this day">
                  {dayRows.map((r) => (
                    <li key={r.key} className="rounded-full border border-surface-border bg-surface px-3 py-1.5 text-sm">
                      <span className="font-semibold text-gray-700">{r.label}</span>
                      <span className="ml-2 font-bold tabular-nums text-heading">{r.bottles.toLocaleString()}</span>
                      <span className="ml-1 text-xs text-gray-400">{r.sharePercent}%</span>
                    </li>
                  ))}
                </ul>
              )}
              {dayRows.length === 0 && !dayReport.isFetching && day && (
                <p className="mt-3 text-sm text-gray-500">No entries on this day{filtered ? " for these filters" : ""}.</p>
              )}
            </div>
          )}
        </div>
      )}
    </Panel>
  );
}

/* ------------------------- deep-dive section ------------------------ */

const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const REGION_COLORS = ["#8b5cf6", "#2aa9bd", "#0f9f78", "#e8a23b", "#e056c2", "#687189"];

function WeekdayChart({ avg }: { avg: number[] }) {
  const max = Math.max(1, ...avg);
  const best = avg.indexOf(Math.max(...avg));
  return (
    <div className="flex h-44 items-end gap-2">
      {avg.map((v, i) => (
        <div key={WEEKDAYS[i]} className="flex h-full flex-1 flex-col items-center justify-end gap-1.5" title={`${WEEKDAYS[i]}: ${v.toFixed(1)} bottles avg`}>
          <span className="text-[11px] font-semibold tabular-nums text-gray-600">{Math.round(v)}</span>
          <div
            className={`w-full rounded-t-md transition-all ${i === best && v > 0 ? "bg-brand-500" : "bg-brand-200"}`}
            style={{ height: `${Math.max(3, (v / max) * 100)}%` }}
          />
          <span className="text-[11px] font-medium text-gray-500">{WEEKDAYS[i]}</span>
        </div>
      ))}
    </div>
  );
}

export function DeepInsights({ insights }: { insights?: DashboardInsights }) {
  const { r60, r30, reg, pending } = useInsightData();

  const weekday = useMemo(() => {
    const tot = Array(7).fill(0) as number[];
    const cnt = Array(7).fill(0) as number[];
    r60.data?.series.forEach((p) => {
      const dow = new Date(`${p.date}T12:00:00`).getDay();
      tot[dow] += p.bottles;
      cnt[dow] += 1;
    });
    return tot.map((t, i) => (cnt[i] ? t / cnt[i] : 0));
  }, [r60.data]);

  const topStores = r30.data?.rows.slice(0, 6) ?? [];
  const maxStore = Math.max(1, ...topStores.map((r) => r.bottles));

  const dormant = insights?.dormantStores ?? [];
  const dormantCount = insights?.dormantLive ?? 0;

  return (
    <>
      <div className="grid gap-6 lg:grid-cols-2">
        <Panel title="Busiest days of the week" action={<span className="text-xs text-gray-400">avg bottles · last 60 days</span>}>
          {r60.isLoading ? <Skeleton className="h-44" /> : <WeekdayChart avg={weekday} />}
        </Panel>

        <Panel title="Volume share by region" action={<PanelLink to="/reports">Full report →</PanelLink>}>
          {reg.isLoading ? (
            <Skeleton className="h-40" />
          ) : !reg.data || reg.data.rows.length === 0 ? (
            <p className="text-sm text-gray-500">No orders in the last 30 days.</p>
          ) : (
            <DonutChart
              centerValue={reg.data.totalBottles.toLocaleString()}
              centerLabel="bottles · 30 days"
              slices={reg.data.rows.map((r, i) => ({ label: r.label, value: r.bottles, color: REGION_COLORS[i % REGION_COLORS.length] }))}
            />
          )}
        </Panel>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Panel title="Top stores · 30 days" action={<PanelLink to="/reports">All stores →</PanelLink>}>
          {r30.isLoading ? (
            <Skeleton className="h-40" />
          ) : topStores.length === 0 ? (
            <p className="text-sm text-gray-500">No orders in the last 30 days.</p>
          ) : (
            <BarList
              items={topStores.map((r) => ({
                label: r.label,
                sub: `${r.sub ?? ""} · ${r.entries} entries · ${r.avgPerEntry} avg`,
                value: r.bottles,
                max: maxStore,
                suffix: " btl",
              }))}
            />
          )}
        </Panel>

        <Panel title="Pending today" action={<PanelLink to="/pending">Open →</PanelLink>}>
          {pending.isLoading ? (
            <Skeleton className="h-40" />
          ) : !pending.data ? null : pending.data.pending === 0 ? (
            <p className="flex items-center gap-2 text-sm font-medium text-status-success">
              <IconCheckCircle className="h-5 w-5" /> All {pending.data.liveStores} live stores are marked.
            </p>
          ) : (
            <>
              <p className="mb-3 text-sm text-gray-600">
                <span className="font-bold text-status-warning">{pending.data.pending}</span> of {pending.data.liveStores} live stores still need an entry.
              </p>
              <ul className="flex flex-col divide-y divide-surface-border">
                {pending.data.items.slice(0, 5).map((s) => (
                  <li key={s.id} className="flex items-center justify-between gap-3 py-2.5 first:pt-0 last:pb-0">
                    <div className="min-w-0">
                      <p className="truncate text-sm font-medium text-gray-900">{s.name}</p>
                      <p className="text-xs text-gray-500">{[s.externalCode, s.city ?? s.state].filter(Boolean).join(" · ")}</p>
                    </div>
                    {s.pocNumber ? (
                      <a href={`tel:${s.pocNumber}`} className="shrink-0 text-xs font-semibold text-brand-600 hover:text-brand-700">
                        {s.pocNumber}
                      </a>
                    ) : (
                      <Badge tone="neutral">no contact</Badge>
                    )}
                  </li>
                ))}
              </ul>
              {pending.data.pending > 5 && <p className="mt-3 text-xs text-gray-400">+ {pending.data.pending - 5} more</p>}
            </>
          )}
        </Panel>
      </div>

      {dormantCount > 0 && (
        <Panel title={`Live stores with no orders in 30 days (${dormantCount})`} action={<PanelLink to="/stores">Stores →</PanelLink>}>
          <div className="flex flex-wrap gap-2">
            {dormant.slice(0, 24).map((s) => (
              <span key={s.id} className="rounded-lg bg-status-warning-soft px-3 py-1.5 text-xs font-medium text-status-warning" title={s.platform ?? ""}>
                {s.name} <span className="opacity-60">{s.externalCode}</span>
              </span>
            ))}
            {dormantCount > dormant.length && <span className="px-2 py-1.5 text-xs text-gray-400">+ {dormantCount - dormant.length} more</span>}
          </div>
        </Panel>
      )}
    </>
  );
}
