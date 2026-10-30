import { Fragment, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Dropdown } from "@/components/ui/Dropdown";
import { Skeleton } from "@/components/feedback/Skeleton";
import { ErrorState } from "@/components/feedback/ErrorState";
import { pushToast } from "@/lib/toast";
import { usePersistentState } from "@/hooks/usePersistentState";
import { usePartners } from "@/features/stores/useStores";
import { useAuth } from "@/features/auth/useAuth";
import { Panel, SegmentedControl } from "@/features/orders/ui";
import { apiRequest } from "@/services/api";

/*
 * Why did a performance number change? Administrators and entry reviewers only (the backend refuses everyone else; this page is just where it is shown).
 * Pick two moments: a stored report, a time rebuilt from the records, or right now. Every employee's change is split into named causes; whatever the
 * records cannot explain is listed as unexplained and marks the report for review. Nothing here changes any data.
 */

type Status = "verified" | "reconciled" | "requires_review" | "unverifiable";
interface Side {
  at: string; snapshot_id: string | null; source: string; snapshot_source: string | null; today: string; as_of: string | null; judged_days: number;
  scope_basis: "live" | "stored" | "current"; revision_of: string | null; revision_reason: string | null;
}
interface Figures { done: number; expected: number; percent: number; stores: number; reported: boolean }
interface Removed {
  kind: "cleared" | "deleted" | "moved"; entry_id: string; store_id: string; store_code: string | null; store_name: string | null; date: string; at: string;
  by: string | null; by_role: string | null; source: string | null; reason: string | null; reason_recorded: boolean; explained: boolean;
}
interface StoreRef { store_id: string; store_code: string | null; store_name: string | null; status?: string }
interface Row {
  employee_id: string; employee_name: string | null; employee_code: string | null; previous: Figures; current: Figures; delta: number; change_percent: number | null; percent_points: number;
  explained: { new_days: number; entries_added: number; entries_removed: number; stores_gained: number; stores_lost: number };
  unexplained: { removed_without_evidence: number; stored_figure_difference: number; arithmetic_gap: number; total: number };
  added_by: Record<string, number>; covered_by: Record<string, number>; covered_via: Record<string, number>;
  /** Entries this person marked (created) between the two moments, in total and per Indian day. */
  made: { total: number; by_day: Record<string, number> };
  /** Entries created in the period on THIS person's stores by someone else, and what share of that person's own entries that is. */
  entered_by_others: { employee_id: string; name: string | null; entries: number; share_of_their_entries: number }[];
  records: { removed: Removed[]; removed_without_evidence: { store_id: string; store_code: string | null; date: string }[]; stores_gained: StoreRef[]; stores_lost: StoreRef[] };
  status: Status; status_label: string; reasons: string[];
}
interface Helper {
  employee_id: string; employee_name: string | null; employee_code: string | null; made: { total: number; by_day: Record<string, number> };
  for_owners: { employee_id: string; name: string | null; code: string | null; entries: number; share_percent: number }[]; unowned_entries: number;
}
interface Reconciliation {
  partner_slug: string; partner_label: string; month: string; definition: Record<string, string>; previous: Side; current: Side;
  notes: string[];
  summary: { status: Status; status_label: string; employees: number; verified: number; reconciled: number; requires_review: number; unverifiable: number; unexplained_total: number };
  employees: Row[];
  /** People with no stores of their own who still entered entries (no percentage): how their entries split across the stores' owners. */
  helpers: Helper[];
}
interface SnapshotItem {
  id: string; generated_at: string; generated_by: string | null; source: "manual" | "scheduled" | "report"; as_of: string | null; employees: number; judged_days: number;
  revision_of: string | null; revision_reason: string | null; revised_by_later: boolean; has_report_text: boolean;
}
interface Verification { status: Status; status_label: string; reproduced: boolean; hash_intact: boolean; notes: string[]; employees: { employee_name: string; reported_done: number; rebuilt_done: number; difference: number; matches: boolean }[] }
interface Timeline { events: { id: string; type: string; at: string; actor: { name: string | null; role: string | null; known: boolean }; reason: string | null; comment: string | null; old: Record<string, unknown> | null; new: Record<string, unknown> | null }[] }

const TONE: Record<Status, "success" | "info" | "danger" | "warning"> = { verified: "success", reconciled: "info", requires_review: "danger", unverifiable: "warning" };
const SOURCE_LABEL = { manual: "Saved by hand", scheduled: "Daily", report: "Copied to send" } as const;
const n = (v: number) => v.toLocaleString("en-IN");
const signed = (v: number) => `${v > 0 ? "+" : v < 0 ? "−" : ""}${n(Math.abs(v))}`;
const when = (iso: string | null) => (iso ? new Date(iso).toLocaleString("en-IN", { timeZone: "Asia/Kolkata", day: "numeric", month: "short", hour: "numeric", minute: "2-digit" }) + " IST" : "-");
const day = (iso: string) => new Date(`${iso}T00:00:00`).toLocaleDateString("en-IN", { day: "numeric", month: "short" });
const shiftMonth = (month: string, by: number) => {
  const [y, m] = month.split("-").map(Number);
  const d = new Date(y, m - 1 + by, 1);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
};
/** "2026-10-29T10:37" typed in the page is a wall-clock time in India. */
const istInstant = (local: string) => (local ? `${local.length === 16 ? `${local}:00` : local}+05:30` : "");

type Pick = "auto" | "now" | "time" | "date" | `snap:${string}`;

function useSnapshots(partner: string, month: string) {
  return useQuery({
    queryKey: ["performance-snapshots", partner, month],
    queryFn: () => apiRequest<{ snapshots: SnapshotItem[] }>(`/orders/performance/snapshots?partner=${encodeURIComponent(partner)}${month ? `&month=${month}` : ""}`, { silent: true }),
    enabled: Boolean(partner),
    staleTime: 0,
  });
}

const todayIst = () => new Date().toLocaleDateString("en-CA", { timeZone: "Asia/Kolkata" });

interface Choice { prev: Pick; prevTime: string; prevDate: string; curr: Pick; currTime: string; currDate: string }

function useReconciliation(partner: string, month: string, c: Choice, employeeId: string) {
  const { prev, prevTime, prevDate, curr, currTime, currDate } = c;
  const ready = Boolean(partner) && (prev !== "time" || prevTime) && (prev !== "date" || prevDate) && (curr !== "time" || currTime) && (curr !== "date" || currDate);
  const params = new URLSearchParams({ partner });
  if (month) params.set("month", month);
  if (prev.startsWith("snap:")) params.set("previous_snapshot", prev.slice(5));
  if (prev === "time") params.set("previous_at", istInstant(prevTime));
  if (prev === "date") params.set("previous_at", `${prevDate}T00:00:00+05:30`);               // from the START of that date
  if (curr.startsWith("snap:")) params.set("current_snapshot", curr.slice(5));
  if (curr === "time") params.set("current_at", istInstant(currTime));
  if (curr === "date" && currDate < todayIst()) params.set("current_at", `${currDate}T23:59:59+05:30`);  // until the END of that date (today = right now)
  if (employeeId) params.set("employee_id", employeeId);
  return useQuery({
    queryKey: ["performance-reconciliation", params.toString()],
    queryFn: () => apiRequest<Reconciliation>(`/orders/performance/reconciliation?${params}`, { silent: true }),
    enabled: Boolean(ready),
    staleTime: 0,
  });
}

/** Everything the history of one entry says (who created it, edited it, cleared it, and why): the same record the Store Audit shows. */
function EntryHistory({ entryId }: { entryId: string }) {
  const q = useQuery({ queryKey: ["entry-history", entryId], queryFn: () => apiRequest<Timeline>(`/entries/${entryId}`, { silent: true }), staleTime: 60_000 });
  if (q.isLoading) return <Skeleton className="mt-2 h-10" />;
  if (q.isError || !q.data) return <p className="mt-2 text-xs text-status-danger">The history of this entry could not be loaded.</p>;
  return (
    <ol className="mt-2 space-y-1 border-l-2 border-surface-border pl-3 text-xs text-gray-700">
      {q.data.events.map((e) => (
        <li key={e.id}>
          <span className="font-bold text-heading">{e.type}</span> · {when(e.at)} · {e.actor.known ? `${e.actor.name ?? "?"}${e.actor.role ? ` (${e.actor.role})` : ""}` : "nobody was signed in"}
          {e.reason ? ` · reason: ${e.reason}` : ""}{e.comment ? ` · ${e.comment}` : ""}
          {e.old || e.new ? <span className="text-gray-500"> · {JSON.stringify(e.old ?? {})} → {JSON.stringify(e.new ?? {})}</span> : null}
        </li>
      ))}
    </ol>
  );
}

function Chip({ children, tone }: { children: React.ReactNode; tone: "up" | "down" | "flat" }) {
  const c = tone === "up" ? "bg-status-success/15 text-status-success" : tone === "down" ? "bg-status-warning-soft text-status-warning" : "bg-surface-muted text-gray-700";
  return <span className={`inline-block whitespace-nowrap rounded-full px-2 py-0.5 text-[11px] font-bold ${c}`}>{children}</span>;
}

function Causes({ r }: { r: Row }) {
  const e = r.explained;
  const items: [string, number, "up" | "down"][] = [
    ["newly finished day", e.new_days, "up"],
    ["entries added", e.entries_added, "up"], ["entries removed", -e.entries_removed, "down"], ["stores gained", e.stores_gained, "up"], ["stores lost", -e.stores_lost, "down"],
  ];
  const shown = items.filter(([, v]) => v !== 0);
  if (!shown.length) return <span className="text-xs text-gray-400">no change</span>;
  return <div className="flex flex-wrap gap-1">{shown.map(([label, v, t]) => <Chip key={label} tone={t}>{signed(v)} {label}</Chip>)}</div>;
}

function Detail({ r }: { r: Row }) {
  const [open, setOpen] = useState<string | null>(null);
  const breakdown = (o: Record<string, number>) => Object.entries(o).sort((a, b) => b[1] - a[1]).map(([k, v]) => `${k}: ${n(v)}`).join(" · ") || "-";
  return (
    <div className="space-y-3 text-xs text-gray-700">
      {r.reasons.length > 0 && <ul className="list-disc space-y-0.5 pl-4">{r.reasons.map((x) => <li key={x}>{x}</li>)}</ul>}
      {r.records.removed.length > 0 && (
        <div>
          <p className="font-bold text-heading">Entries that lost their store-day ({r.records.removed.length})</p>
          <ul className="mt-1 space-y-1.5">
            {r.records.removed.map((x) => (
              <li key={x.entry_id} className="rounded-lg border border-surface-border bg-surface p-2">
                <span className="font-semibold text-gray-900">{x.store_name ?? x.store_code ?? x.store_id}</span> · {day(x.date)} · {x.kind === "moved" ? "moved to another date or store" : x.kind === "cleared" ? "cleared" : "deleted"} {when(x.at)}
                {" · "}{x.by ? <>by <b>{x.by}</b>{x.by_role ? ` (${x.by_role})` : ""}</> : <b className="text-status-danger">nobody was signed in, so who removed it is not recorded</b>}
                {x.reason_recorded ? ` · reason: ${x.reason}` : <span className="text-gray-400"> · no reason recorded</span>}
                <button type="button" className="ml-2 font-semibold text-brand-600 hover:text-brand-700" aria-expanded={open === x.entry_id} onClick={() => setOpen(open === x.entry_id ? null : x.entry_id)}>
                  {open === x.entry_id ? "Hide history" : "Open history"}
                </button>
                {open === x.entry_id && <EntryHistory entryId={x.entry_id} />}
              </li>
            ))}
          </ul>
        </div>
      )}
      {r.records.removed_without_evidence.length > 0 && (
        <p className="rounded-lg border border-status-danger/40 bg-status-danger-soft p-2 text-status-danger">
          {r.records.removed_without_evidence.length} store-day{r.records.removed_without_evidence.length === 1 ? "" : "s"} lost an entry and the records do not say how:{" "}
          {r.records.removed_without_evidence.slice(0, 12).map((x) => `${x.store_code ?? x.store_id.slice(0, 8)} ${day(x.date)}`).join(", ")}{r.records.removed_without_evidence.length > 12 ? "…" : ""}
        </p>
      )}
      {(r.records.stores_gained.length > 0 || r.records.stores_lost.length > 0) && (
        <p>
          Stores that changed hands: {r.records.stores_gained.length > 0 && <>gained {r.records.stores_gained.slice(0, 8).map((s) => s.store_name ?? s.store_code).join(", ")}{r.records.stores_gained.length > 8 ? `… (${r.records.stores_gained.length})` : ""}. </>}
          {r.records.stores_lost.length > 0 && <>lost {r.records.stores_lost.slice(0, 8).map((s) => s.store_name ?? s.store_code).join(", ")}{r.records.stores_lost.length > 8 ? `… (${r.records.stores_lost.length})` : ""}.</>}
        </p>
      )}
      <p>
        <b className="text-heading">Entries they marked in this period: {n(r.made.total)}</b>
        {Object.keys(r.made.by_day).length > 0 ? <span> · {Object.entries(r.made.by_day).map(([d, v]) => `${day(d)}: ${n(v)}`).join(" · ")}</span> : <span className="text-gray-500"> (none)</span>}
        <span className="text-gray-500"> (counted by the day they were entered, in any of the platform&apos;s stores, including any cleared since)</span>
      </p>
      {r.entered_by_others.length > 0 && (
        <p>
          <b className="text-heading">Entered on their stores in this period by others:</b>{" "}
          {r.entered_by_others.map((o) => `${o.name ?? "?"} ${n(o.entries)} (${o.share_of_their_entries}% of ${o.name ?? "their"} entries)`).join(" · ")}
        </p>
      )}
      <p><b className="text-heading">Who entered the entries now counted for this employee:</b> {breakdown(r.covered_by)}</p>
      <p><b className="text-heading">Where they came from:</b> {breakdown(r.covered_via)} <span className="text-gray-500">(for audit only: who or what entered an entry never decides whether it counts)</span></p>
      {Object.keys(r.added_by).length > 0 && <p><b className="text-heading">Who entered the entries added since the earlier report:</b> {breakdown(r.added_by)}</p>}
    </div>
  );
}

function SnapshotRow({ s, partner, month, onUse }: { s: SnapshotItem; partner: string; month: string; onUse: (side: "prev" | "curr", id: string) => void }) {
  const qc = useQueryClient();
  const [verification, setVerification] = useState<Verification | null>(null);
  const [revising, setRevising] = useState(false);
  const [reason, setReason] = useState("");
  const verify = useMutation({
    mutationFn: () => apiRequest<Verification>(`/orders/performance/snapshots/${s.id}?partner=${encodeURIComponent(partner)}`),
    onSuccess: setVerification,
  });
  const revise = useMutation({
    mutationFn: () => apiRequest("/orders/performance/snapshots", { method: "POST", body: { partner, month, source: "manual", revision_of: s.id, revision_reason: reason } }),
    onSuccess: () => { pushToast("Revised report saved. The original is unchanged.", "success"); setRevising(false); setReason(""); void qc.invalidateQueries({ queryKey: ["performance-snapshots"] }); },
  });
  return (
    <li className="px-4 py-3 text-sm sm:px-5">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <span className="font-semibold text-heading">{when(s.generated_at)}</span>
        <Badge tone="neutral">{SOURCE_LABEL[s.source]}</Badge>
        {s.revision_of && <Badge tone="info">Revision</Badge>}
        {s.revised_by_later && <Badge tone="warning">Revised later</Badge>}
        <span className="text-xs text-gray-500">{s.generated_by ?? "system"} · {s.judged_days} days counted</span>
        <span className="ml-auto flex flex-wrap gap-1.5">
          <Button size="sm" variant="secondary" onClick={() => onUse("prev", s.id)}>As earlier</Button>
          <Button size="sm" variant="secondary" onClick={() => onUse("curr", s.id)}>As later</Button>
          <Button size="sm" variant="secondary" disabled={verify.isPending} onClick={() => verify.mutate()}>Check against the records</Button>
          <Button size="sm" variant="secondary" onClick={() => setRevising((v) => !v)}>Revise…</Button>
        </span>
      </div>
      {s.revision_reason && <p className="mt-1 text-xs text-gray-600">Revised because: {s.revision_reason}</p>}
      {verification && (
        <p className={`mt-1 text-xs font-semibold ${verification.reproduced && verification.hash_intact ? "text-status-success" : "text-status-danger"}`}>
          {verification.status_label}: {verification.reproduced ? "every figure is reproduced by the records of that moment" : `${verification.employees.filter((e) => !e.matches).map((e) => `${e.employee_name} stored ${n(e.reported_done)}, the records give ${n(e.rebuilt_done)}`).join("; ") || "the judged days differ"}`}
          {!verification.hash_intact ? " · the stored content no longer matches its fingerprint" : ""}
          {verification.notes.map((x) => ` · ${x}`)}
        </p>
      )}
      {revising && (
        <form className="mt-2 flex flex-wrap items-center gap-2" onSubmit={(e) => { e.preventDefault(); if (reason.trim()) revise.mutate(); }}>
          <input value={reason} onChange={(e) => setReason(e.target.value)} maxLength={1000} placeholder="Why is this report being revised?" aria-label="Reason for the revision" className="h-9 min-w-[16rem] flex-1 rounded-lg border border-surface-border bg-surface px-3 text-sm" />
          <Button size="sm" type="submit" disabled={!reason.trim() || revise.isPending}>Save revised report now</Button>
          <span className="text-xs text-gray-500">Saves today&apos;s figures as a new report that points back at this one. This one is never changed.</span>
        </form>
      )}
    </li>
  );
}

export function PerformanceReconcilePage() {
  const qc = useQueryClient();
  const { user, hasRole, hasPermission } = useAuth();
  // Administrators and entry reviewers see everyone and the platform-wide saved reports; a Team Lead sees only their own team and no saved reports (the backend enforces both).
  const fullAudit = hasRole("admin") || hasRole("developer") || hasPermission("entries.audit");
  const { data: fetched = [] } = usePartners(fullAudit || hasPermission("orders.overview"));
  const partners = fullAudit || hasPermission("orders.overview") ? fetched : user?.platformSlug ? [{ slug: user.platformSlug, name: user.platformLabel ?? user.platformSlug }] : [];
  const [pickedPartner, setPartner] = usePersistentState<string>("orders.platform", "");
  const partner = partners.some((p) => p.slug === pickedPartner) ? pickedPartner : (partners[0]?.slug ?? "");
  const [month, setMonth] = useState("");
  const [prev, setPrev] = useState<Pick>("auto");
  const [curr, setCurr] = useState<Pick>("now");
  const [prevTime, setPrevTime] = useState("");
  const [currTime, setCurrTime] = useState("");
  const [prevDate, setPrevDate] = useState("");
  const [currDate, setCurrDate] = useState("");
  const [employee, setEmployee] = useState("");
  const [open, setOpen] = useState<string | null>(null);

  const snaps = useSnapshots(fullAudit ? partner : "", month);
  const rq = useReconciliation(partner, month, { prev, prevTime, prevDate, curr, currTime, currDate }, employee);
  // A date has to fall inside the month being shown; the last day it may reach is today (India).
  const monthFirst = `${(month || new Date().toLocaleDateString("en-CA", { timeZone: "Asia/Kolkata" }).slice(0, 7))}-01`;
  const dateMax = (() => { const [y, m] = monthFirst.slice(0, 7).split("-").map(Number); const last = `${monthFirst.slice(0, 7)}-${String(new Date(y, m, 0).getDate()).padStart(2, "0")}`; return last < todayIst() ? last : todayIst(); })();
  const d = rq.data;
  const shownMonth = d?.month ?? month;
  const thisMonth = (() => { const t = new Date(); return `${t.getFullYear()}-${String(t.getMonth() + 1).padStart(2, "0")}`; })();
  const save = useMutation({
    mutationFn: () => apiRequest("/orders/performance/snapshots", { method: "POST", body: { partner, month: month || undefined, source: "manual" } }),
    onSuccess: () => { pushToast("Report saved as it stands now.", "success"); void qc.invalidateQueries({ queryKey: ["performance-snapshots"] }); },
  });

  const pickOptions = useMemo(() => {
    const list = (snaps.data?.snapshots ?? []).map((s) => ({ value: `snap:${s.id}`, label: `${when(s.generated_at)} · ${SOURCE_LABEL[s.source]}${s.revision_of ? " · revision" : ""}` }));
    return list;
  }, [snaps.data]);
  const prevOptions = [{ value: "auto", label: "The previous day (24 hours before the later one)" }, { value: "date", label: "A date I choose (from the start of that day)" }, ...pickOptions, { value: "time", label: "A time I choose (rebuilt from the records)" }];
  const currOptions = [{ value: "now", label: "Right now" }, { value: "date", label: "A date I choose (until the end of that day)" }, ...pickOptions, { value: "time", label: "A time I choose (rebuilt from the records)" }];
  const employeeOptions = [{ value: "", label: "All employees" }, ...(d?.employees ?? []).map((e) => ({ value: e.employee_id, label: `${e.employee_name ?? "?"} (${e.employee_code ?? ""})` }))];
  const use = (side: "prev" | "curr", id: string) => (side === "prev" ? setPrev(`snap:${id}`) : setCurr(`snap:${id}`));

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-center gap-3">
        <Link to="/orders/performance" className="text-sm font-semibold text-brand-600 hover:text-brand-700">‹ Performance</Link>
        {partners.length > 1 && <SegmentedControl label="Platform" value={partner} onChange={(v) => { setPartner(v); setOpen(null); setEmployee(""); setPrev("auto"); setCurr("now"); }} options={partners.map((p) => ({ value: p.slug, label: p.name }))} />}
        <div className="ml-auto flex items-center gap-1">
          <Button size="sm" variant="secondary" aria-label="Previous month" disabled={!shownMonth} onClick={() => { setMonth(shiftMonth(shownMonth, -1)); setPrev("auto"); setCurr("now"); }}>‹</Button>
          <span className="min-w-[8rem] text-center text-sm font-extrabold text-heading">{shownMonth || "…"}</span>
          <Button size="sm" variant="secondary" aria-label="Next month" disabled={!shownMonth || shownMonth >= thisMonth} onClick={() => { setMonth(shiftMonth(shownMonth, 1)); setPrev("auto"); setCurr("now"); }}>›</Button>
        </div>
      </div>

      <Panel title="Compare two reports" subtitle="Each employee's number is recounted every time it is looked at. Pick an earlier and a later moment to see exactly why a number changed.">
        <div className="grid gap-3 md:grid-cols-3">
          <label className="block text-xs font-semibold text-gray-600">Earlier
            <Dropdown aria-label="Earlier report" value={prev} onValueChange={(v) => setPrev(v as Pick)} options={prevOptions} className="mt-1 w-full" />
            {prev === "date" && <input type="date" aria-label="Earlier date" min={monthFirst} max={dateMax} value={prevDate} onChange={(e) => setPrevDate(e.target.value)} className="mt-1 h-9 w-full rounded-lg border border-surface-border bg-surface px-2 text-sm" />}
            {prev === "time" && <input type="datetime-local" aria-label="Earlier time (IST)" value={prevTime} onChange={(e) => setPrevTime(e.target.value)} className="mt-1 h-9 w-full rounded-lg border border-surface-border bg-surface px-2 text-sm" />}
          </label>
          <label className="block text-xs font-semibold text-gray-600">Later
            <Dropdown aria-label="Later report" value={curr} onValueChange={(v) => setCurr(v as Pick)} options={currOptions} className="mt-1 w-full" />
            {curr === "date" && <input type="date" aria-label="Later date" min={monthFirst} max={dateMax} value={currDate} onChange={(e) => setCurrDate(e.target.value)} className="mt-1 h-9 w-full rounded-lg border border-surface-border bg-surface px-2 text-sm" />}
            {curr === "time" && <input type="datetime-local" aria-label="Later time (IST)" value={currTime} onChange={(e) => setCurrTime(e.target.value)} className="mt-1 h-9 w-full rounded-lg border border-surface-border bg-surface px-2 text-sm" />}
          </label>
          <label className="block text-xs font-semibold text-gray-600">Employee
            <Dropdown aria-label="Employee" value={employee} onValueChange={setEmployee} options={employeeOptions} searchable className="mt-1 w-full" />
          </label>
        </div>
        <p className="mt-2 text-xs text-gray-500">Times are Indian time. A time you choose is rebuilt from the entry records (created, cleared, moved) of that moment.</p>
      </Panel>

      {rq.isLoading && <Skeleton className="h-64 !rounded-2xl" />}
      {rq.isError && <ErrorState message={(rq.error as Error)?.message || "Couldn't load the reconciliation."} onRetry={() => rq.refetch()} />}

      {d && (
        <>
          <section className="rounded-2xl border border-surface-border bg-surface p-4 shadow-card sm:p-5" aria-live="polite">
            <div className="flex flex-wrap items-center gap-3">
              <Badge tone={TONE[d.summary.status]} dot>{d.summary.status_label}</Badge>
              <span className="text-sm text-gray-600">
                {d.summary.employees} employee{d.summary.employees === 1 ? "" : "s"}: {d.summary.verified} verified · {d.summary.reconciled} reconciled · {d.summary.requires_review} need review · {d.summary.unverifiable} unverifiable
                {d.summary.unexplained_total > 0 ? ` · ${n(d.summary.unexplained_total)} store-days unexplained` : ""}
              </span>
            </div>
            <div className="mt-3 grid gap-3 text-xs text-gray-600 sm:grid-cols-2">
              {([["Earlier", d.previous], ["Later", d.current]] as const).map(([label, s]) => (
                <div key={label} className="rounded-lg bg-surface-subtle p-3">
                  <p className="font-bold text-heading">{label}: {when(s.at)}</p>
                  <p>{s.source}{s.snapshot_source ? ` (${SOURCE_LABEL[s.snapshot_source as keyof typeof SOURCE_LABEL]})` : ""} · {s.judged_days} days counted{s.as_of ? `, up to ${day(s.as_of)}` : ""}</p>
                  {s.revision_of && <p className="font-semibold text-brand-700">Revision of an earlier report: {s.revision_reason}</p>}
                  <p>Employee stores: {s.scope_basis === "stored" ? "as stored with the report" : s.scope_basis === "live" ? "as they are now" : "assumed to be as they are now (not recorded for that moment)"}</p>
                </div>
              ))}
            </div>
            {d.notes.map((x) => <p key={x} className="mt-2 text-xs text-status-warning">{x}</p>)}
          </section>

          <Panel flush title="Employees" subtitle="Worst first. Open a row for the records behind it.">
            <div className="overflow-x-auto">
              <table className="w-full min-w-[820px] text-sm">
                <thead>
                  <tr className="border-b border-surface-border bg-surface-subtle text-left text-xs font-semibold uppercase tracking-wide text-gray-500">
                    <th className="px-5 py-3">Employee</th><th className="px-4 py-3">Earlier</th><th className="px-4 py-3">Later</th><th className="px-4 py-3" title="Entries gained (+) or lost (-). Under it: the change as a share of the earlier entries (%), and how far the performance percentage itself moved (pts = percentage points, e.g. 54.3% to 56.0% is +1.7 pts)">Change</th><th className="px-4 py-3" title="Entries this person marked (created) between the two moments, whoever's stores they were">Marked by them</th>
                    <th className="px-4 py-3">What explains it</th><th className="px-4 py-3">Unexplained</th><th className="px-4 py-3">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {d.employees.length === 0 && <tr><td colSpan={8} className="px-4 py-12 text-center text-gray-500">No employee has a figure at these moments.</td></tr>}
                  {d.employees.map((r) => (
                    <Fragment key={r.employee_id}>
                      <tr className="cursor-pointer border-b border-surface-border hover:bg-surface-subtle/70" onClick={() => setOpen(open === r.employee_id ? null : r.employee_id)} aria-expanded={open === r.employee_id}>
                        <td className="px-5 py-3"><div className="font-semibold text-gray-900">{r.employee_name ?? "?"}</div><div className="text-xs text-gray-500">{r.employee_code}</div></td>
                        <td className="px-4 py-3 tabular-nums">{n(r.previous.done)} <span className="text-gray-400">/ {n(r.previous.expected)}</span><div className="text-xs text-gray-500">{r.previous.percent}%{r.previous.reported ? "" : " · rebuilt"}</div></td>
                        <td className="px-4 py-3 tabular-nums">{n(r.current.done)} <span className="text-gray-400">/ {n(r.current.expected)}</span><div className="text-xs text-gray-500">{r.current.percent}%{r.current.reported ? "" : " · rebuilt"}</div></td>
                        <td className="px-4 py-3 font-bold tabular-nums">{signed(r.delta)}<div className="text-xs font-medium text-gray-500">{r.change_percent === null ? "" : `${signed(r.change_percent)}%`} · {r.percent_points > 0 ? "+" : ""}{r.percent_points} pts</div><div className="text-[10px] font-normal text-gray-400">pts = percentage points</div></td>
                        <td className="px-4 py-3 font-bold tabular-nums text-heading">{n(r.made.total)}</td>
                        <td className="px-4 py-3"><Causes r={r} /></td>
                        <td className={`px-4 py-3 font-bold tabular-nums ${r.unexplained.total ? "text-status-danger" : "text-gray-400"}`}>{r.unexplained.total ? n(r.unexplained.total) : "0"}</td>
                        <td className="px-4 py-3"><Badge tone={TONE[r.status]}>{r.status_label}</Badge></td>
                      </tr>
                      {open === r.employee_id && <tr className="border-b border-surface-border bg-surface-subtle/50"><td colSpan={8} className="px-5 py-4"><Detail r={r} /></td></tr>}
                    </Fragment>
                  ))}
                </tbody>
              </table>
            </div>
          </Panel>

          {d.helpers.length > 0 && (
            <Panel flush title="Entered for others" subtitle="People with no stores of their own, so no percentage, who still marked entries in this period: how many, and whose stores they went to.">
              <ul className="divide-y divide-surface-border">
                {d.helpers.map((h) => (
                  <li key={h.employee_id} className="px-4 py-3 text-sm sm:px-5">
                    <div className="flex flex-wrap items-baseline gap-x-3">
                      <span className="font-semibold text-heading">{h.employee_name ?? "?"}</span>
                      <span className="text-xs text-gray-500">{h.employee_code}</span>
                      <span className="ml-auto font-bold tabular-nums text-heading">{n(h.made.total)} <span className="text-xs font-medium text-gray-500">entries marked</span></span>
                    </div>
                    <ul className="mt-1.5 space-y-0.5 text-xs text-gray-700">
                      {h.for_owners.map((o) => (
                        <li key={o.employee_id}>For <b>{o.name ?? "?"}</b>&apos;s stores: <span className="font-semibold tabular-nums">{n(o.entries)}</span> ({o.share_percent}% of {h.employee_name ?? "their"} entries)</li>
                      ))}
                      {h.unowned_entries > 0 && <li className="text-status-warning">On stores nobody owns: {n(h.unowned_entries)}</li>}
                    </ul>
                    {Object.keys(h.made.by_day).length > 0 && <p className="mt-1 text-xs text-gray-500">{Object.entries(h.made.by_day).map(([dt, v]) => `${day(dt)}: ${n(v)}`).join(" · ")}</p>}
                  </li>
                ))}
              </ul>
            </Panel>
          )}

          <p className="text-xs text-gray-500">What the numbers mean: {d.definition.entries}. Judged days: {d.definition.judged_days}.</p>
        </>
      )}

      {fullAudit && <Panel flush title="Reports kept" subtitle="What each report said when it was made. Never edited or deleted; a correction is a new report that points back at the old one."
        action={<Button size="sm" disabled={save.isPending || !partner} onClick={() => save.mutate()}>Save the report as it is now</Button>}>
        {snaps.isLoading && <Skeleton className="m-4 h-16" />}
        {snaps.isError && <div className="p-4"><ErrorState message="Couldn't load the saved reports." onRetry={() => snaps.refetch()} /></div>}
        {snaps.data && snaps.data.snapshots.length === 0 && <p className="px-5 py-8 text-center text-sm text-gray-500">No report has been kept for this month yet. One is kept every morning, and one each time an administrator copies a report to send it.</p>}
        <ul className="divide-y divide-surface-border">
          {(snaps.data?.snapshots ?? []).map((s) => <SnapshotRow key={s.id} s={s} partner={partner} month={shownMonth} onUse={use} />)}
        </ul>
      </Panel>}
    </div>
  );
}
