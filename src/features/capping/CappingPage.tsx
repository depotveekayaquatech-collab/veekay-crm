import { useMemo, useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { PageHeader } from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { SelectField } from "@/components/ui/Dropdown";
import { Modal } from "@/components/ui/Modal";
import { Skeleton } from "@/components/feedback/Skeleton";
import { ErrorState } from "@/components/feedback/ErrorState";
import { EmptyState } from "@/components/feedback/EmptyState";
import { IconEdit, IconRefresh, IconSearch, IconUpload } from "@/components/ui/icons";
import { useAuth } from "@/features/auth/useAuth";
import { pushToast } from "@/lib/toast";
import {
  getCappingReport, importCapsFile, setStoreCap, syncCapsFromSheet,
  type CapImportResult, type CapLevel, type CapRow,
} from "@/services/capping";

const field =
  "h-10 w-full rounded-lg border border-surface-border bg-surface px-3 text-sm shadow-sm outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20";

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
      <span className="text-[11px] font-bold uppercase tracking-wider text-gray-500">{label}</span>
      <span className={`text-2xl font-extrabold tabular-nums ${tone}`}>{value.toLocaleString("en-IN")}</span>
    </button>
  );
}

function UsageBar({ row }: { row: CapRow }) {
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

/** Pick a store (or arrive from a row), type its daily cap, save. One store at a time. The monthly limit is the daily cap x 30. */
function EditCapModal({ rows, initial, onClose }: { rows: CapRow[]; initial: CapRow | null; onClose: () => void }) {
  const qc = useQueryClient();
  const [storeId, setStoreId] = useState(initial?.storeId ?? "");
  const [text, setText] = useState(initial?.dailyCap?.toString() ?? "");
  const store = rows.find((r) => r.storeId === storeId) ?? null;
  const sorted = useMemo(() => [...rows].sort((a, b) => a.outletName.localeCompare(b.outletName)), [rows]);

  const save = useMutation({
    mutationFn: (cap: number | null) => setStoreCap(storeId, cap),
    onSuccess: (_d, cap) => {
      pushToast(cap === null ? "Cap removed." : "Cap saved.", "success");
      void qc.invalidateQueries({ queryKey: ["capping"] });
      onClose();
    },
  });

  const parsed = text.trim() === "" ? null : Number(text);
  const invalid = parsed !== null && (!Number.isInteger(parsed) || parsed < 0 || parsed > 1_000_000);

  function submit(e: FormEvent) {
    e.preventDefault();
    if (!storeId || invalid || save.isPending) return;
    save.mutate(parsed);
  }

  return (
    <Modal
      open
      onClose={onClose}
      title="Set daily cap"
      description="Bottles per day, as in the capping sheet. The most a store may take in a month is this number × 30. It applies to every month until changed."
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
          {store?.dailyCap !== null && store?.dailyCap !== undefined && (
            <Button variant="secondary" onClick={() => save.mutate(null)} disabled={save.isPending}>Remove cap</Button>
          )}
          <Button onClick={() => save.mutate(parsed)} isLoading={save.isPending} disabled={!storeId || invalid || parsed === null}>Save cap</Button>
        </>
      }
    >
      <form onSubmit={submit} className="flex flex-col gap-4">
        <label className="flex flex-col gap-1.5 text-[13px] font-semibold text-gray-700">
          Store
          <SelectField
            className={field}
            value={storeId}
            onChange={(e) => {
              const id = e.target.value;
              setStoreId(id);
              setText(rows.find((r) => r.storeId === id)?.dailyCap?.toString() ?? "");
            }}
          >
            <option value="">Choose a store…</option>
            {sorted.map((r) => (
              <option key={r.storeId} value={r.storeId}>{r.outletName} ({r.outletId}){r.city ? ` · ${r.city}` : ""}</option>
            ))}
          </SelectField>
        </label>
        {store && (
          <p className="rounded-lg bg-surface-subtle px-3 py-2 text-xs text-gray-600">
            {store.city ?? "—"}, {store.state ?? "—"} · used this month: <b>{n(store.used)}</b> bottles · current cap: <b>{n(store.dailyCap)}</b> a day (<b>{n(store.monthlyCap)}</b> a month)
          </p>
        )}
        <label className="flex flex-col gap-1.5 text-[13px] font-semibold text-gray-700">
          Daily cap (bottles per day)
          <input
            className={field}
            inputMode="numeric"
            value={text}
            onChange={(e) => setText(e.target.value.replace(/[^\d]/g, ""))}
            placeholder="e.g. 300"
            aria-invalid={invalid}
          />
          <span className="text-xs font-normal text-gray-500">0 is allowed (no bottles). Leave empty and use “Remove cap” for no limit.</span>
        </label>
        {!invalid && parsed !== null && <p className="text-sm text-gray-600">Monthly limit: <b>{(parsed * 30).toLocaleString("en-IN")}</b> bottles ({parsed.toLocaleString("en-IN")} × 30).</p>}
        {invalid && <p role="alert" className="text-sm text-status-danger">Enter a whole number from 0 to 1,000,000.</p>}
        <button type="submit" className="hidden" />
      </form>
    </Modal>
  );
}

/** Developers and administrators: load caps from an uploaded sheet (developers can also read the Google Capping sheet). */
function LoadCaps({ onDone, canSyncSheet }: { onDone: () => void; canSyncSheet: boolean }) {
  // An upload exists to change caps, so replacing the ones already set is the default.
  const [overwrite, setOverwrite] = useState(true);
  const [result, setResult] = useState<CapImportResult | null>(null);
  const sheet = useMutation({ mutationFn: () => syncCapsFromSheet(overwrite), onSuccess: (r) => { setResult(r); onDone(); } });
  const file = useMutation({ mutationFn: (f: File) => importCapsFile(f, overwrite), onSuccess: (r) => { setResult(r); onDone(); } });
  return (
    <section className="rounded-xl border border-surface-border bg-surface p-4 shadow-card">
      <h3 className="text-sm font-bold text-gray-900">Upload the capping sheet</h3>
      <p className="mt-1 text-xs text-gray-500">
        A .csv or .xlsx with an <b>Outlet Name</b> (or <b>Outlet ID</b>) column and a <b>Capping</b> column with the <b>daily</b> number per store. The monthly limit is that × 30;
        alerts compare each store's bottles so far with the daily number × the day of the month. Employees can still change a single store by hand.
      </p>
      <div className="mt-3 flex flex-wrap items-center gap-3">
        <label className="flex items-center gap-2 text-sm font-medium text-gray-700">
          <input type="checkbox" className="h-4 w-4 accent-brand-500" checked={overwrite} onChange={(e) => setOverwrite(e.target.checked)} />
          Overwrite caps already set in the CRM
        </label>
        {canSyncSheet && (
          <Button size="sm" variant="secondary" onClick={() => sheet.mutate()} isLoading={sheet.isPending}>
            <IconRefresh className="h-3.5 w-3.5" /> Fetch from Google sheet
          </Button>
        )}
        <label className="inline-flex cursor-pointer items-center gap-1.5 rounded-lg border border-surface-border bg-surface px-3 py-1.5 text-sm font-semibold text-gray-700 hover:bg-surface-subtle">
          <IconUpload className="h-3.5 w-3.5" /> {file.isPending ? "Uploading…" : "Upload sheet"}
          <input type="file" accept=".csv,.xlsx,.xlsm" className="sr-only" onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ""; if (f) file.mutate(f); }} />
        </label>
      </div>
      {result && (
        <div className="mt-3 rounded-lg bg-surface-subtle p-3 text-sm text-gray-700">
          {result.added} added · {result.updated} updated · {result.kept} unchanged · {result.rowsRead} rows read
          {result.readAs ? <p className="mt-1 text-xs text-gray-500">Read as: {result.readAs}.</p> : null}
          {result.warnings.length > 0 && (
            <ul className="mt-2 list-disc space-y-1 pl-5 text-xs text-status-warning">{result.warnings.map((w, i) => <li key={i}>{w}</li>)}</ul>
          )}
        </div>
      )}
    </section>
  );
}

export function CappingPage() {
  const { hasPermission } = useAuth();
  const [month, setMonth] = useState<string>("");
  const [q, setQ] = useState("");
  const [filter, setFilter] = useState<Filter>("ALL");
  const [state, setState] = useState("");
  const [city, setCity] = useState("");
  const [sort, setSort] = useState<Sort>("level");
  const [editing, setEditing] = useState<CapRow | "pick" | null>(null);
  const [limit, setLimit] = useState({ n: PAGE, sig: "" });
  const qc = useQueryClient();

  const { data, isLoading, isError, error, refetch, isFetching } = useQuery({
    queryKey: ["capping", month],
    queryFn: () => getCappingReport(month || undefined),
    staleTime: 30_000,
    // never show the previous month's rows as if they were the chosen month's
    placeholderData: undefined,
  });

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
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Capping"
        subtitle={data ? `${data.monthLabel} · every live Zepto store · monthly limit = daily cap × 30 · warns when ahead of pace and at ${data.warnPercent}% of the limit` : "Bottles used against each store's monthly cap."}
        action={
          <div className="flex flex-wrap items-center gap-2">
            <SelectField className="h-10 rounded-lg border border-surface-border bg-surface px-3 text-sm shadow-sm" value={month || data?.month || ""} onChange={(e) => setMonth(e.target.value)} aria-label="Month">
              {(data?.months ?? [data?.month ?? ""]).filter(Boolean).map((m) => (
                <option key={m} value={m}>{new Date(`${m}-01T12:00:00`).toLocaleDateString("en-IN", { month: "long", year: "numeric" })}</option>
              ))}
            </SelectField>
            <Button variant="secondary" onClick={() => { void qc.invalidateQueries({ queryKey: ["capping"] }); void refetch(); }} isLoading={isFetching && !isLoading}>
              <IconRefresh className="h-4 w-4" /> Refresh
            </Button>
            <Button onClick={() => setEditing("pick")} disabled={!rows.length}>
              <IconEdit className="h-4 w-4" /> Set a cap
            </Button>
          </div>
        }
      />

      {(hasPermission("sheets.sync") || hasPermission("orders.correct")) && (
        <LoadCaps canSyncSheet={hasPermission("sheets.sync")} onDone={() => void qc.invalidateQueries({ queryKey: ["capping"] })} />
      )}

      {isLoading && <Skeleton className="h-64" />}
      {isError && <ErrorState message={error instanceof Error ? error.message : "Couldn't load the capping report."} onRetry={() => refetch()} />}

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

          {shown.length === 0 ? (
            <EmptyState title="No stores match" description={rows.length ? "Change the search or filters." : "There are no live Zepto stores yet."} />
          ) : (
            <div className="stacked-table overflow-x-auto rounded-xl border border-surface-border bg-surface shadow-card">
              <table className="w-full min-w-[1000px] border-collapse text-sm">
                <thead>
                  <tr className="bg-surface-subtle/80 text-left text-[11px] font-bold uppercase tracking-wider text-gray-500">
                    {["Store", "State / City", "Daily cap", "Monthly limit", "Used", "Left", "Usage", "Status", "Owner", ""].map((h) => (
                      <th key={h} className="border-b border-surface-border px-3 py-3 first:pl-4">{h}</th>
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
                        {r.alert === "AHEAD" && <p className="text-xs font-semibold text-status-warning">{n(r.aheadBy)} ahead of today's {n(r.allowedToDate)}</p>}
                      </td>
                      <td data-label="Usage" className="px-3 py-3"><UsageBar row={r} /></td>
                      <td data-label="Status" className="px-3 py-3"><Badge tone={LEVEL[r.alert].tone}>{LEVEL[r.alert].label}</Badge></td>
                      <td data-label="Owner" className="px-3 py-3 text-gray-600">{r.ownerName ?? "—"}</td>
                      <td data-label="" className="px-3 py-3 text-right">
                        <Button size="sm" variant="secondary" onClick={() => setEditing(r)} aria-label={`Edit cap for ${r.outletName}`}>
                          <IconEdit className="h-3.5 w-3.5" /> Edit cap
                        </Button>
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

      {editing && <EditCapModal rows={rows} initial={editing === "pick" ? null : editing} onClose={() => setEditing(null)} />}
    </div>
  );
}
