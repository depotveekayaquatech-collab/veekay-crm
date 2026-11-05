import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { SelectField } from "@/components/ui/Dropdown";
import { Badge } from "@/components/ui/Badge";
import { EmptyState } from "@/components/feedback/EmptyState";
import { ErrorState } from "@/components/feedback/ErrorState";
import { Skeleton } from "@/components/feedback/Skeleton";
import { IconSearch } from "@/components/ui/icons";
import { usePersistentState } from "@/hooks/usePersistentState";
import { dayLabel } from "@/features/capping/helpers";
import { field } from "@/features/capping/styles";
import { getCappingOverflow, type OverflowRow } from "@/services/capping";

const n = (v: number) => v.toLocaleString("en-IN");
const PRIORITY_KEY = "capping.priorityStores";

function Card({ label, value, sub, tone }: { label: string; value: string; sub?: string; tone: string }) {
  return (
    <div className="flex flex-col gap-1 rounded-xl border border-surface-border bg-surface p-4 shadow-card">
      <span className="text-[11px] font-bold text-gray-500">{label}</span>
      <span className={`text-2xl font-extrabold tabular-nums ${tone}`}>{value}</span>
      {sub && <span className="text-xs text-gray-500">{sub}</span>}
    </div>
  );
}

function Star({ on, name, onToggle }: { on: boolean; name: string; onToggle: () => void }) {
  return (
    <button type="button" onClick={onToggle} aria-pressed={on} aria-label={`${on ? "Remove" : "Mark"} ${name} as priority`}
      className={`rounded-md px-1.5 py-1 text-lg leading-none transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 ${on ? "text-status-warning" : "text-gray-300 hover:text-gray-500"}`}>
      {on ? "★" : "☆"}
    </button>
  );
}

function StoreCell({ r }: { r: OverflowRow }) {
  return (
    <>
      <p className="break-words font-semibold text-gray-900">{r.outletName}</p>
      <p className="break-all text-xs text-gray-500">{r.outletId}{r.city || r.state ? ` · ${[r.city, r.state].filter(Boolean).join(", ")}` : ""}</p>
    </>
  );
}

function OverTable({ rows, priority, toggle }: { rows: OverflowRow[]; priority: Set<string>; toggle: (id: string) => void }) {
  const [open, setOpen] = useState<string | null>(null);
  return (
    <div className="stacked-table overflow-x-auto rounded-xl border border-surface-border bg-surface shadow-card">
      <table className="w-full min-w-[820px] border-collapse text-sm">
        <thead>
          <tr className="bg-surface-subtle/80 text-left text-[11px] font-bold text-gray-500">
            {["", "Store", "Daily cap", "Monthly limit", "Used", "Over the month", "Days over daily cap"].map((h, i) => <th key={i} className="border-b border-surface-border px-3 py-3 first:pl-4">{h}</th>)}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.storeId} className="border-b border-surface-border/60 align-top hover:bg-surface-subtle/50">
              <td data-label="" className="px-3 py-3 pl-4"><Star on={priority.has(r.storeId)} name={r.outletName} onToggle={() => toggle(r.storeId)} /></td>
              <td data-label="Store" className="max-w-[260px] px-3 py-3"><StoreCell r={r} /></td>
              <td data-label="Daily cap" className="px-3 py-3 tabular-nums">{r.dailyCap === null ? "—" : n(r.dailyCap)}</td>
              <td data-label="Monthly limit" className="px-3 py-3 tabular-nums">{r.monthlyCap === null ? "—" : n(r.monthlyCap)}</td>
              <td data-label="Used" className="px-3 py-3 font-semibold tabular-nums">{n(r.used)}</td>
              <td data-label="Over the month" className="px-3 py-3 tabular-nums">{r.excess ? <span className="font-semibold text-status-danger">+{n(r.excess)}</span> : <span className="text-gray-400">—</span>}</td>
              <td data-label="Days over daily cap" className="px-3 py-3">
                {r.daysOver === 0 ? <span className="text-gray-400">—</span> : (
                  <>
                    <button type="button" aria-expanded={open === r.storeId} onClick={() => setOpen((cur) => (cur === r.storeId ? null : r.storeId))} className="font-semibold text-brand-600 hover:text-brand-700">
                      {r.daysOver} day{r.daysOver === 1 ? "" : "s"} · +{n(r.dailyExcess)} bottles
                    </button>
                    {open === r.storeId && (
                      <ul className="mt-2 space-y-0.5 text-xs text-gray-600">
                        {r.overDays.map((d) => <li key={d.date} className="tabular-nums">{dayLabel(d.date)}: {n(d.bottles)} against {n(d.cap)} (+{n(d.overBy)})</li>)}
                      </ul>
                    )}
                  </>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function RoomTable({ rows, priority, toggle }: { rows: OverflowRow[]; priority: Set<string>; toggle: (id: string) => void }) {
  return (
    <div className="stacked-table overflow-x-auto rounded-xl border border-surface-border bg-surface shadow-card">
      <table className="w-full min-w-[720px] border-collapse text-sm">
        <thead>
          <tr className="bg-surface-subtle/80 text-left text-[11px] font-bold text-gray-500">
            {["", "Store", "Monthly limit", "Used", "Room left", "Usage"].map((h, i) => <th key={i} className="border-b border-surface-border px-3 py-3 first:pl-4">{h}</th>)}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.storeId} className="border-b border-surface-border/60 hover:bg-surface-subtle/50">
              <td data-label="" className="px-3 py-3 pl-4"><Star on={priority.has(r.storeId)} name={r.outletName} onToggle={() => toggle(r.storeId)} /></td>
              <td data-label="Store" className="max-w-[260px] px-3 py-3"><StoreCell r={r} /></td>
              <td data-label="Monthly limit" className="px-3 py-3 tabular-nums">{r.monthlyCap === null ? "—" : n(r.monthlyCap)}</td>
              <td data-label="Used" className="px-3 py-3 tabular-nums">{n(r.used)}</td>
              <td data-label="Room left" className="px-3 py-3 font-semibold tabular-nums text-status-success">{n(r.room)}</td>
              <td data-label="Usage" className="px-3 py-3 tabular-nums text-gray-600">{r.percent === null ? "—" : `${r.percent}%`}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/**
 * Overflow and room, read-only: the Zepto stores over their capping (for the month, and day by day against the capping in force that day) next to the stores that still
 * have room under their monthly limit. Star a store to keep your priority stores on top of the room list. It changes no entry and moves no bottle: it is the picture to plan
 * supply with, and to take to the platform when a capping needs to change.
 */
export function OverflowTab({ month }: { month: string }) {
  const [q, setQ] = useState("");
  const [state, setState] = useState("");
  const [priorityOnly, setPriorityOnly] = useState(false);
  const [saved, setSaved] = usePersistentState<string>(PRIORITY_KEY, "");
  const priority = useMemo(() => new Set(saved.split(",").filter(Boolean)), [saved]);
  const toggle = (id: string) => setSaved((priority.has(id) ? [...priority].filter((x) => x !== id) : [...priority, id]).join(","));

  const { data, isLoading, isError, error, refetch } = useQuery({ queryKey: ["capping", "overflow", month], queryFn: () => getCappingOverflow(month), staleTime: 30_000 });
  const states = useMemo(() => [...new Set((data?.rows ?? []).map((r) => r.state).filter(Boolean) as string[])].sort(), [data]);

  const { over, room } = useMemo(() => {
    const needle = q.trim().toLowerCase();
    const rows = (data?.rows ?? []).filter(
      (r) => (!state || r.state === state) && (!priorityOnly || priority.has(r.storeId)) && (!needle || r.outletName.toLowerCase().includes(needle) || r.outletId.toLowerCase().includes(needle)),
    );
    return {
      over: rows.filter((r) => r.excess > 0 || r.daysOver > 0),
      room: rows.filter((r) => r.room > 0).sort((a, b) => Number(priority.has(b.storeId)) - Number(priority.has(a.storeId)) || b.room - a.room || a.outletName.localeCompare(b.outletName)),
    };
  }, [data, q, state, priorityOnly, priority]);
  const s = data?.summary;

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-xs text-gray-500">
          {data ? `${data.monthLabel} · read-only: nothing here changes an entry or moves a bottle · monthly limit = daily capping × the days in the month` : "Stores over their capping, and stores with room."}
        </p>
      </div>

      {isLoading && <Skeleton className="h-64" />}
      {isError && <ErrorState message={error instanceof Error ? error.message : "Couldn't load the overflow."} onRetry={() => refetch()} />}

      {data && s && (
        <>
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
            <Card label="Stores over the month" value={n(s.storesOverMonth)} sub={`${n(s.monthExcess)} bottles above their limit`} tone="text-status-danger" />
            <Card label="Stores over on a day" value={n(s.storesOverDays)} sub={`${n(s.daysOver)} store-days, ${n(s.dailyExcess)} bottles above the day's cap`} tone="text-status-warning" />
            <Card label="Stores with room" value={n(s.storesWithRoom)} tone="text-status-success" />
            <Card label="Room left" value={n(s.room)} sub="bottles under the monthly limits" tone="text-status-success" />
            <Card label="Used of limit" value={`${n(s.used)} / ${n(s.limit)}`} sub={`${n(s.stores)} live stores`} tone="text-gray-800" />
          </div>

          <section className="rounded-xl border border-surface-border bg-surface p-4 shadow-card">
            <div className="grid gap-3 sm:grid-cols-3">
              <label className="relative">
                <IconSearch className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" />
                <input className={`${field} pl-9`} value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search store name or Outlet ID" aria-label="Search stores" />
              </label>
              <SelectField className={field} value={state} onChange={(e) => setState(e.target.value)} aria-label="State">
                <option value="">All states</option>
                {states.map((x) => <option key={x} value={x}>{x}</option>)}
              </SelectField>
              <button type="button" aria-pressed={priorityOnly} onClick={() => setPriorityOnly((v) => !v)}
                className={`h-10 rounded-lg px-3 text-sm font-semibold ring-1 ring-surface-border ${priorityOnly ? "bg-brand-500 text-white" : "bg-surface text-gray-600 hover:bg-surface-subtle"}`}>
                ★ Priority stores only ({priority.size})
              </button>
            </div>
            <p className="mt-2 text-xs text-gray-500">Stars are kept on this device only and are not shared with anyone.</p>
          </section>

          <section className="flex flex-col gap-2">
            <h2 className="flex items-center gap-2 text-sm font-bold text-gray-800">Over their capping <Badge tone="danger">{over.length}</Badge></h2>
            {over.length === 0 ? <EmptyState title="No store is over" description="Nothing matches, or every store stayed within its capping." /> : <OverTable rows={over} priority={priority} toggle={toggle} />}
          </section>

          <section className="flex flex-col gap-2">
            <h2 className="flex items-center gap-2 text-sm font-bold text-gray-800">Room under the monthly limit <Badge tone="success">{room.length}</Badge></h2>
            <p className="text-xs text-gray-500">Starred stores first, then the most room.</p>
            {room.length === 0 ? <EmptyState title="No store has room" description="Nothing matches, or no store with a capping has anything left." /> : <RoomTable rows={room} priority={priority} toggle={toggle} />}
          </section>
        </>
      )}
    </div>
  );
}
