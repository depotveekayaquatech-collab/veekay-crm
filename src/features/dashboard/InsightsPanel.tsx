/**
 * Deeper admin-dashboard insights. All numbers come from the existing
 * /orders/report + /orders/pending + /orders/insights endpoints — nothing
 * here is computed from made-up data.
 */
import { useMemo, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { Badge } from "@/components/ui/Badge";
import { Skeleton } from "@/components/feedback/Skeleton";
import { AreaChart, BarList, DonutChart } from "@/features/dashboard/charts";
import { IconAlertTriangle, IconCheckCircle } from "@/components/ui/icons";
import { daysAgo } from "@/lib/dates";
import { usePending, useReport } from "@/services/reports";
import type { DashboardInsights } from "@/types/order";

/* ---------------------------- shared bits --------------------------- */

function Panel({ title, action, children, className = "" }: { title: string; action?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={`rounded-xl border border-surface-border bg-white shadow-card ${className}`}>
      <header className="flex items-center justify-between gap-3 border-b border-surface-border/80 px-5 py-4">
        <h3 className="text-sm font-bold text-gray-900">{title}</h3>
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
  const r60 = useReport(daysAgo(59), end, "store");
  const r30 = useReport(daysAgo(29), end, "store");
  const reg = useReport(daysAgo(29), end, "region");
  const pending = usePending(0, "");
  return { r60, r30, reg, pending };
}

/* --------------------------- alert strip ---------------------------- */

export function AlertStrip({ insights }: { insights?: DashboardInsights }) {
  const { r30, pending } = useInsightData();

  const dormant = useMemo(() => {
    if (!insights || !r30.data) return [];
    const active = new Set(r30.data.rows.map((r) => r.sub));
    return insights.allStores.filter((s) => s.status === "LIVE" && !active.has(s.externalCode));
  }, [insights, r30.data]);

  const lagging = insights?.platforms.filter((p) => p.totalStores > 0 && p.percent < 50) ?? [];
  const notLive = insights ? insights.storeStatus.PENDING + insights.storeStatus.CLOSE : 0;

  const items: { key: string; tone: "warning" | "danger" | "info"; text: string; to?: string }[] = [];
  if (pending.data && pending.data.pending > 0)
    items.push({ key: "pending", tone: "warning", text: `${pending.data.pending} live store${pending.data.pending > 1 ? "s" : ""} not marked today`, to: "/pending" });
  lagging.forEach((p) =>
    items.push({ key: p.slug, tone: "danger", text: `${p.label} is at ${Math.round(p.percent)}% completion today`, to: "/orders/overview" }),
  );
  if (dormant.length > 0)
    items.push({ key: "dormant", tone: "warning", text: `${dormant.length} live store${dormant.length > 1 ? "s" : ""} with no orders in 30 days`, to: "/stores" });
  if (notLive > 0) items.push({ key: "notlive", tone: "info", text: `${notLive} store${notLive > 1 ? "s" : ""} not live yet`, to: "/stores" });

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
    <div className="flex flex-wrap items-center gap-2 rounded-xl border border-surface-border bg-white px-4 py-3 shadow-card">
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
    <div className={`tile tile-${tone} rounded-xl border border-surface-border bg-white p-5 shadow-card transition-all duration-200 hover:-translate-y-0.5 hover:shadow-md`}>
      <p className="text-[11px] font-bold uppercase tracking-wider text-gray-500">{label}</p>
      {loading ? (
        <Skeleton className="mt-2 h-8 w-20" />
      ) : (
        <p className="mt-1.5 text-[1.7rem] font-bold leading-none tabular-nums text-ink-900">{value}</p>
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
  const activeStores = r30.data?.rows.length ?? 0;
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

const RANGES = [14, 30, 60] as const;

export function TrendCard() {
  const { r60 } = useInsightData();
  const [range, setRange] = useState<(typeof RANGES)[number]>(30);
  const series = r60.data?.series.slice(-range) ?? [];
  const total = sum(series.map((p) => p.bottles));
  const peak = series.reduce((b, p) => (p.bottles > b.bottles ? p : b), { label: "—", bottles: 0 });

  return (
    <Panel
      title="Bottle volume trend"
      action={
        <div className="flex gap-1 rounded-lg bg-surface-muted p-1">
          {RANGES.map((r) => (
            <button
              key={r}
              onClick={() => setRange(r)}
              className={`rounded-md px-2.5 py-1 text-xs font-semibold transition-all ${range === r ? "bg-white text-brand-700 shadow-sm" : "text-gray-500 hover:text-gray-800"}`}
            >
              {r}d
            </button>
          ))}
        </div>
      }
    >
      {r60.isLoading ? (
        <Skeleton className="h-48" />
      ) : (
        <>
          <div className="mb-3 flex flex-wrap gap-x-6 gap-y-1 text-xs text-gray-500">
            <span><span className="font-semibold tabular-nums text-gray-900">{total.toLocaleString()}</span> bottles in period</span>
            <span>Peak <span className="font-semibold text-gray-900">{peak.bottles}</span> on {peak.label}</span>
          </div>
          <AreaChart data={series.map((p) => ({ label: p.label, value: p.bottles }))} valueSuffix=" bottles" />
        </>
      )}
    </Panel>
  );
}

/* ------------------------- deep-dive section ------------------------ */

const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const REGION_COLORS = ["#2f6fed", "#2aa9bd", "#0f7b57", "#d99a2b", "#8fb0fc", "#687189"];

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

  const dormant = useMemo(() => {
    if (!insights || !r30.data) return [];
    const active = new Set(r30.data.rows.map((r) => r.sub));
    return insights.allStores.filter((s) => s.status === "LIVE" && !active.has(s.externalCode));
  }, [insights, r30.data]);

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

      {dormant.length > 0 && (
        <Panel title={`Live stores with no orders in 30 days (${dormant.length})`} action={<PanelLink to="/stores">Stores →</PanelLink>}>
          <div className="flex flex-wrap gap-2">
            {dormant.slice(0, 24).map((s) => (
              <span key={s.id} className="rounded-lg bg-status-warning-soft px-3 py-1.5 text-xs font-medium text-status-warning" title={s.platform ?? ""}>
                {s.name} <span className="opacity-60">{s.externalCode}</span>
              </span>
            ))}
            {dormant.length > 24 && <span className="px-2 py-1.5 text-xs text-gray-400">+ {dormant.length - 24} more</span>}
          </div>
        </Panel>
      )}
    </>
  );
}
