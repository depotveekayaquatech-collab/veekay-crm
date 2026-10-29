import { Fragment, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Dropdown } from "@/components/ui/Dropdown";
import { IconCheckCircle, IconDownload, IconUsers } from "@/components/ui/icons";
import { Skeleton } from "@/components/feedback/Skeleton";
import { ErrorState } from "@/components/feedback/ErrorState";
import { downloadCsv } from "@/lib/csv";
import { pushToast } from "@/lib/toast";
import { copyText } from "@/lib/clipboard";
import { formatReport, pickEmployees, type Who } from "@/lib/performanceReport";
import { usePersistentState } from "@/hooks/usePersistentState";
import { Link, Navigate } from "react-router-dom";
import { useAuth } from "@/features/auth/useAuth";
import { usePartners } from "@/features/stores/useStores";
import { Avatar, FilterChip, Panel, ProgressBar, ProgressRing, SearchBox, SegmentedControl, StatCard } from "@/features/orders/ui";
import { apiRequest } from "@/services/api";
import { useVendorPerformance, VendorPerformance } from "@/features/orders/VendorPerformance";

interface Day { date: string; done: number; expected: number; percent: number; cumulative: number }
interface Row {
  employee_id: string; employee_code: string; employee_name: string; region_name: string | null;
  stores: number; expected: number; done: number; missing: number; percent: number; yesterday_percent: number | null; daily: Day[];
  /** Everything this person entered on the platform this month, in any store. */
  entries_made: number;
  /** No store of their own: no percentage, only the entries they made. */
  no_stores: boolean;
  /** Entries whose number this person changed this month (a Team Lead's job). */
  corrected: number;
  is_team_lead: boolean;
}
interface Performance {
  /** Whose performance this is: everyone, the caller's team (a Team Lead), or only the caller. */
  view: "all" | "team" | "self";
  partner_slug: string; partner_label: string; month: string; month_label: string; from: string | null; as_of: string | null; days: number; today: string;
  summary: { employees: number; stores: number; expected: number; done: number; percent: number; below_50: number };
  employees: Row[];
}

interface PendingStores {
  employee_id: string; employee_name: string; employee_code: string; date: string; from: string | null; holiday: string | null; scope_stores: number;
  judged_days: number; missing_total: number;
  /** False when the month is closed to this person (they can look, only an admin can mark). */
  month_open: boolean;
  stores: { store_id: string; store_name: string; external_code: string; crm_code: string | null; state: string | null; city: string | null; vendor_name: string | null; can_open: boolean; missing_days: number; missing_dates: string[] }[];
}

function usePendingStores(partner: string, employeeId: string, date: string) {
  return useQuery({
    queryKey: ["performance-pending", partner, employeeId, date],
    queryFn: () => apiRequest<PendingStores>(`/orders/performance/pending?partner=${encodeURIComponent(partner)}&employee_id=${employeeId}&date=${date}`),
    refetchOnWindowFocus: true,
    staleTime: 0,
  });
}

function usePerformance(partner: string, month: string, enabled = true) {
  return useQuery({
    queryKey: ["performance", partner, month],
    queryFn: () => apiRequest<Performance>(`/orders/performance?partner=${encodeURIComponent(partner)}${month ? `&month=${month}` : ""}`),
    enabled: enabled && Boolean(partner),
    refetchOnWindowFocus: true,
    staleTime: 0,
  });
}

// Green only when nothing is missing (100%); yellow from 99.9% down to 70%; red below 70%. The server never rounds a day that is short of 100% up to 100.
const tone = (p: number): "success" | "warning" | "danger" => (p >= 100 ? "success" : p >= 70 ? "warning" : "danger");
const dayChip = (p: number) => (p >= 100 ? "bg-status-success/15 text-status-success" : p >= 70 ? "bg-yellow-500/20 text-yellow-800 dark:text-yellow-300" : "bg-status-danger-soft text-status-danger");
const shortDay = (iso: string) => new Date(`${iso}T00:00:00`).toLocaleDateString("en-IN", { day: "numeric", month: "short" });

/**
 * The stores holding the percentage below 100 UP TO the chosen day: every store with a counted day still unmarked from the 1st to that day, with the dates it
 * is missing. Marking them all brings the employee to 100% as of that day. A store opens its calendar at that month, ready to mark.
 */
function PendingForDay({ partner, employeeId, date }: { partner: string; employeeId: string; date: string }) {
  const q = usePendingStores(partner, employeeId, date);
  const month = date.slice(0, 7);
  if (q.isLoading) return <Skeleton className="mt-3 h-24" />;
  if (q.isError || !q.data) return <div className="mt-3"><ErrorState message="Couldn't load the pending stores." onRetry={() => q.refetch()} /></div>;
  const d = q.data;
  const range = d.from && d.from !== date ? `${shortDay(d.from)} to ${shortDay(date)}` : shortDay(date);
  return (
    <div className="mt-3 rounded-xl border border-surface-border bg-surface p-3" aria-live="polite">
      <p className="text-sm font-bold text-heading">
        {d.stores.length === 0
          ? `${range}: nothing left to mark, 100% as of ${shortDay(date)}`
          : `${range}: ${d.missing_total} day${d.missing_total === 1 ? "" : "s"} still to mark in ${d.stores.length} store${d.stores.length === 1 ? "" : "s"}`}
      </p>
      {d.stores.length > 0 && (
        <p className="mt-0.5 text-xs text-gray-500">
          Marking all of these takes the percentage to 100% as of {shortDay(date)}.{" "}
          {d.month_open ? "Pick a store to open its calendar and mark its missing days." : "This month is closed for entries, so you can look at these stores but only an admin can mark them now."}
        </p>
      )}
      <ul className="mt-2 grid gap-1.5 sm:grid-cols-2 lg:grid-cols-3">
        {d.stores.map((s) => {
          const body = (
            <>
              <span className="flex items-start justify-between gap-2">
                <span className="block truncate text-sm font-semibold text-gray-900">{s.store_name}</span>
                <span className="shrink-0 rounded-full bg-status-warning-soft px-2 py-0.5 text-[11px] font-bold text-status-warning">{s.missing_days} day{s.missing_days === 1 ? "" : "s"}</span>
              </span>
              <span className="block truncate text-xs text-gray-500">{[s.external_code, s.city, s.state].filter(Boolean).join(" · ")}{s.vendor_name ? ` · ${s.vendor_name}` : ""}</span>
              <span className="mt-0.5 block text-xs text-gray-600">Missing: {s.missing_dates.map(shortDay).join(", ")}</span>
            </>
          );
          return (
            <li key={s.store_id}>
              {s.can_open ? (
                <Link to={`/orders?store=${s.store_id}&month=${month}`} className="block rounded-lg border border-surface-border px-3 py-2 hover:border-brand-500 hover:bg-surface-subtle focus-visible:outline focus-visible:outline-2 focus-visible:outline-brand-500">{body}</Link>
              ) : (
                <div className="rounded-lg border border-dashed border-surface-border px-3 py-2" title="Not one of your own stores, so you can't open it here">{body}</div>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function shiftMonth(month: string, by: number): string {
  const [y, m] = month.split("-").map(Number);
  const d = new Date(y, m - 1 + by, 1);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

/** Pick who to include (everyone, under 50%, under 85%, or one employee), then copy the text or download it to paste into the office group. */
function GroupReport({ d }: { d: Performance }) {
  const [who, setWho] = useState<Who>("all");
  const [show, setShow] = useState(false);
  const picked = useMemo(() => pickEmployees(d.employees, who), [d.employees, who]);
  const heading = `${d.partner_label} - Employee performance, ${d.month_label}${d.days ? ` (${shortDay(d.from!)} to ${shortDay(d.as_of!)})` : ""}`;
  const text = useMemo(() => formatReport(heading, picked), [heading, picked]);
  const options = [
    { value: "all", label: `All employees (${d.employees.length})` },
    { value: "under50", label: `Under 50% (${pickEmployees(d.employees, "under50").length})` },
    { value: "under85", label: `Under 85% (${pickEmployees(d.employees, "under85").length})` },
    ...d.employees.map((e) => ({ value: `emp:${e.employee_id}`, label: `${e.employee_name} (${e.employee_code})` })),
  ];

  async function copy() {
    const ok = await copyText(text);
    pushToast(ok ? `Report copied for ${picked.length} employee${picked.length === 1 ? "" : "s"}. Paste it in the group.` : "Couldn't copy. Open the preview and copy it by hand.", ok ? "success" : "error");
  }
  function download() {
    const url = URL.createObjectURL(new Blob([text], { type: "text/plain;charset=utf-8" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = `performance-report-${d.partner_slug}-${d.month}.txt`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 30_000);
  }

  return (
    <div className="mt-4 rounded-xl border border-surface-border bg-surface-subtle/60 p-3">
      <p className="text-xs font-bold uppercase tracking-wide text-gray-500">Report for the group</p>
      <div className="mt-2 flex flex-wrap items-center gap-2">
        <Dropdown aria-label="Who to include" value={who} onValueChange={(v) => setWho(v as Who)} options={options} searchable className="w-full sm:w-72" />
        <Button size="sm" onClick={() => void copy()} disabled={!picked.length}>Copy report</Button>
        <Button size="sm" variant="secondary" onClick={download} disabled={!picked.length}>
          <IconDownload className="h-3.5 w-3.5" aria-hidden="true" />
          Download .txt
        </Button>
        <button type="button" className="text-xs font-semibold text-brand-600 hover:text-brand-700" onClick={() => setShow((v) => !v)} aria-expanded={show}>
          {show ? "Hide preview" : "Preview"}
        </button>
      </div>
      {!picked.length && <p className="mt-2 text-xs text-gray-500">Nobody matches this choice.</p>}
      {show && picked.length > 0 && <textarea readOnly value={text} rows={Math.min(14, text.split("\n").length + 1)} className="mt-2 w-full resize-y rounded-lg border border-surface-border bg-surface p-3 font-mono text-xs" aria-label="Report preview" />}
    </div>
  );
}

/**
 * Performance: for each employee, the share of the entries they should have marked this month (every live store in their scope, every finished day)
 * that they have marked. It is recounted from the entries on every look, from the 1st to yesterday, so days marked late lift the days before them.
 */
export function PerformancePage() {
  const { hasRole } = useAuth();
  // A platform login (Blinkit / Zepto account) is not shown Veekay's vendors.
  return hasRole("partner") ? <Navigate to="/orders" replace /> : <PerformanceBody />;
}

/**
 * Everyone who marks entries sees the Vendors view for their own stores. Only people with the daily overview also get the Employees view and the
 * platform switch (employees cannot list the platforms, so they use the one on their profile).
 */
function PerformanceBody() {
  const { user, hasPermission } = useAuth();
  const overview = hasPermission("orders.overview");
  const [pickedDay, setPickedDay] = useState<{ employeeId: string; date: string } | null>(null);
  const { data: fetched = [] } = usePartners(overview);
  const partners = overview ? fetched : user?.platformSlug ? [{ slug: user.platformSlug, name: user.platformLabel ?? user.platformSlug }] : [];
  const [pickedPartner, setPartner] = usePersistentState<string>("orders.platform", "");
  const [month, setMonth] = useState("");                         // "" = the server's default (the month of yesterday)
  const partner = partners.some((p) => p.slug === pickedPartner) ? pickedPartner : (partners[0]?.slug ?? "");
  const [chosenView, setView] = usePersistentState<"employees" | "vendors">("performance.view", "employees");
  const view = chosenView;                                       // everyone sees both; what the Employees view lists depends on the person (see `d.view`)
  const q = usePerformance(partner, month, view === "employees");
  const vq = useVendorPerformance(partner, month, view === "vendors");
  const [query, setQuery] = useState("");
  const [behindOnly, setBehindOnly] = useState(false);
  const [open, setOpen] = useState<string | null>(null);
  const d = q.data;
  const alone = d?.view === "self";                                // an employee sees only themselves: their row is open, with no team tools
  const openId = alone ? (d?.employees[0]?.employee_id ?? null) : open;

  const rows = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return (d?.employees ?? []).filter((e) => (!behindOnly || (!e.no_stores && e.percent < 50)) && (!needle || e.employee_name.toLowerCase().includes(needle) || e.employee_code.toLowerCase().includes(needle) || (e.region_name ?? "").toLowerCase().includes(needle)));
  }, [d, query, behindOnly]);

  const shown = view === "vendors" ? vq.data : d;                 // whichever list is on screen decides the month label
  const current = shown?.month ?? month;
  const thisMonth = (() => { const n = new Date(); return `${n.getFullYear()}-${String(n.getMonth() + 1).padStart(2, "0")}`; })();

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-center gap-3">
        {partners.length > 1 && <SegmentedControl label="Platform" value={partner} onChange={(v) => { setPartner(v); setOpen(null); setPickedDay(null); }} options={partners.map((p) => ({ value: p.slug, label: p.name }))} />}
        <SegmentedControl label="View" value={view} onChange={(v) => setView(v as "employees" | "vendors")} options={[{ value: "employees", label: "Employees" }, { value: "vendors", label: "Vendors" }]} />
        <div className="ml-auto flex items-center gap-1">
          <Button size="sm" variant="secondary" aria-label="Previous month" disabled={!current} onClick={() => setMonth(shiftMonth(current, -1))}>‹</Button>
          <span className="min-w-[8rem] text-center text-sm font-extrabold text-heading">{shown?.month_label ?? "…"}</span>
          <Button size="sm" variant="secondary" aria-label="Next month" disabled={!current || current >= thisMonth} onClick={() => setMonth(shiftMonth(current, 1))}>›</Button>
        </div>
      </div>

      {view === "vendors" && <VendorPerformance q={vq} />}

      {view === "employees" && q.isLoading && <Skeleton className="h-64 !rounded-2xl" />}
      {view === "employees" && q.isError && <ErrorState message="Couldn't load the performance." onRetry={() => q.refetch()} />}

      {view === "employees" && d && (
        <>
          <section className="relative overflow-hidden rounded-2xl border border-surface-border bg-surface p-4 shadow-card sm:p-6">
            <span aria-hidden="true" className="pointer-events-none absolute -right-12 -top-16 h-52 w-52 rounded-full bg-gradient-to-br from-brand-500/15 to-aqua-400/10 blur-2xl" />
            <div className="relative flex flex-wrap items-center gap-x-8 gap-y-5">
              <ProgressRing percent={d.summary.percent} size={128} sublabel="marked" />
              <div className="min-w-[14rem] flex-1">
                <p className="text-xs font-bold uppercase tracking-[0.14em] text-brand-600">{d.partner_label}</p>
                <h3 className="mt-0.5 text-xl font-extrabold text-heading">{d.month_label}</h3>
                <p className="mt-1 text-sm text-gray-500">
                  {d.view === "team" ? "Your team: you and the people who report to you. " : alone ? "Your own performance. " : ""}
                  {d.days === 0
                    ? "No day of this month has finished yet."
                    : <>Counted from {shortDay(d.from!)} to {shortDay(d.as_of!)} ({d.days} day{d.days === 1 ? "" : "s"}). Recounted from the entries every time you open this page, so days an employee marks late raise their earlier days too.</>}
                </p>
                <div className="mt-4 flex flex-wrap items-center gap-2">
                  <Button size="sm" variant="secondary" disabled={!rows.length} onClick={() =>
                    downloadCsv(`performance-${d.partner_slug}-${d.month}.csv`,
                      ["Employee code", "Employee", "Region", "Stores", "Should mark", "Marked", "Missing", "Performance %", "Entries made (all stores)", "Entries corrected", ...(d.employees.find((x) => x.daily.length)?.daily ?? []).map((x) => x.date)],
                      rows.map((e) => [e.employee_code, e.employee_name, e.region_name, e.stores, e.expected, e.done, e.missing, e.no_stores ? "" : e.percent, e.entries_made, e.corrected, ...e.daily.map((x) => x.percent)]))}>
                    <IconDownload className="h-3.5 w-3.5" aria-hidden="true" />
                    Export CSV
                  </Button>
                </div>
                {!alone && <GroupReport d={d} />}
              </div>
            </div>
          </section>

          <div className="grid gap-4 sm:grid-cols-3">
            <StatCard label="Entries marked" value={`${d.summary.done.toLocaleString()} / ${d.summary.expected.toLocaleString()}`} tone="aqua" icon={IconCheckCircle}>
              <ProgressBar percent={d.summary.percent} strict className="mt-3" />
            </StatCard>
            <StatCard label={`${d.partner_label} overall`} value={`${d.summary.percent}%`} hint={`${d.summary.stores.toLocaleString()} live stores, each day counted once`} tone="brand" icon={IconCheckCircle} />
            {alone ? <StatCard label="Missing" value={(d.employees[0]?.missing ?? 0).toLocaleString()} hint="store-days still to mark this month" tone={(d.employees[0]?.missing ?? 0) > 0 ? "warning" : "success"} icon={IconUsers} /> : <StatCard label="Under 50%" value={d.summary.below_50} hint={d.summary.below_50 > 0 ? "employees behind this month" : "everyone is on track"} tone={d.summary.below_50 > 0 ? "warning" : "success"} icon={IconUsers} />}
          </div>

          <Panel
            flush
            title={alone ? "You" : <>Employees <span className="ml-1 font-medium text-gray-400">{rows.length}</span></>}
            subtitle={alone ? "Covered = an entry exists for your stores, whoever entered it. Tap a day to see the stores still to mark up to that day." : "Lowest first. Entries made = typed in by that person. Covered = an entry exists for their stores, whoever entered it. Open a row to see every day, and tap a day to see the stores still to mark up to that day."}
            action={alone ? undefined : (
              <div className="flex flex-wrap items-center gap-2">
                <FilterChip active={behindOnly} onClick={() => setBehindOnly((v) => !v)} count={d.summary.below_50}>Under 50% only</FilterChip>
                <SearchBox hotkey value={query} onChange={setQuery} placeholder="Search employee, code or region" className="w-full sm:w-64" />
              </div>
            )}
          >
            <div className="overflow-x-auto">
              <table className="w-full min-w-[720px] text-sm">
                <thead>
                  <tr className="border-b border-surface-border bg-surface-subtle text-left text-xs font-semibold uppercase tracking-wide text-gray-500">
                    <th className="px-5 py-3">Employee</th><th className="px-4 py-3">Stores</th><th className="px-4 py-3" title="Entries this person typed in themselves this month, in any store of the platform">Entries made by them</th>
                    <th className="px-4 py-3" title="Store-days of THIS person's stores that have an entry, whoever entered it, out of the store-days they should have">Their stores covered / needed</th>
                    <th className="px-4 py-3">Missing</th><th className="w-64 px-4 py-3">Performance</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.length === 0 && <tr><td colSpan={6} className="px-4 py-12 text-center text-gray-500">No employees match.</td></tr>}
                  {rows.map((e) => (
                    <Fragment key={e.employee_id}>
                      <tr className="cursor-pointer border-b border-surface-border hover:bg-surface-subtle/70" onClick={() => { setOpen(open === e.employee_id ? null : e.employee_id); setPickedDay(null); }}>
                        <td className="px-5 py-3">
                          <div className="flex items-center gap-3">
                            <Avatar name={e.employee_name} />
                            <div className="min-w-0">
                              <div className="truncate font-semibold text-gray-900">{e.employee_name}</div>
                              <div className="text-xs text-gray-500">{e.employee_code}{e.region_name ? ` · ${e.region_name}` : ""}{e.is_team_lead ? " · Team Lead" : ""}</div>
                              {(e.is_team_lead || e.corrected > 0) && <div className="text-xs font-semibold text-brand-700">{e.corrected.toLocaleString()} {e.corrected === 1 ? "entry" : "entries"} corrected</div>}
                            </div>
                          </div>
                        </td>
                        <td className="px-4 py-3 tabular-nums">{e.stores}</td>
                        <td className="px-4 py-3 font-bold tabular-nums text-heading">{e.entries_made.toLocaleString()}</td>
                        {e.no_stores ? (
                          <td colSpan={3} className="px-4 py-3 text-xs text-gray-500">No store of their own, so there is no percentage.</td>
                        ) : (
                          <>
                            <td className="px-4 py-3 tabular-nums">{e.done.toLocaleString()} <span className="text-gray-400">/ {e.expected.toLocaleString()}</span></td>
                            <td className="px-4 py-3 font-bold tabular-nums">{e.missing.toLocaleString()}</td>
                            <td className="px-4 py-3">
                              <div className="flex items-center gap-3">
                                <ProgressBar percent={e.percent} strict className="min-w-[6rem] flex-1" />
                                <Badge tone={tone(e.percent)}>{e.percent}%</Badge>
                              </div>
                            </td>
                          </>
                        )}
                      </tr>
                      {openId === e.employee_id && !e.no_stores && (
                        <tr className="border-b border-surface-border bg-surface-subtle/50">
                          <td colSpan={6} className="px-5 py-4">
                            <p className="mb-2 text-xs font-semibold text-gray-700">Entered by {e.employee_name} this month, in any store of {d.partner_label}: <span className="tabular-nums">{e.entries_made.toLocaleString()}</span></p>
                            <p className="mb-2 text-xs font-semibold text-gray-500">Each day: the share of this employee's stores that have an entry for that day today. The small number is their average from the 1st up to that day. Tap a day to see every store still to mark from the 1st up to that day.</p>
                            <div className="flex flex-wrap gap-1.5">
                              {e.daily.map((x) => {
                                const picked = pickedDay?.employeeId === e.employee_id && pickedDay.date === x.date;
                                return (
                                  <button key={x.date} type="button" aria-pressed={picked} onClick={() => setPickedDay(picked ? null : { employeeId: e.employee_id, date: x.date })}
                                    title={`${shortDay(x.date)}: ${x.done} of ${x.expected} stores marked · average so far ${x.cumulative}%${x.cumulative < 100 ? " · tap to see the stores still to mark up to this day" : ""}`}
                                    className={`rounded-lg px-2.5 py-1.5 text-center text-xs font-semibold transition focus-visible:outline focus-visible:outline-2 focus-visible:outline-brand-500 ${dayChip(x.percent)} ${picked ? "ring-2 ring-brand-600" : "hover:brightness-95"}`}>
                                    <span className="block text-[10px] opacity-70">{shortDay(x.date)}</span>
                                    {x.percent}%
                                    <span className="block text-[10px] opacity-70">avg {x.cumulative}%</span>
                                  </button>
                                );
                              })}
                            </div>
                            {pickedDay?.employeeId === e.employee_id && e.daily.some((x) => x.date === pickedDay.date) && (
                              <PendingForDay partner={partner} employeeId={e.employee_id} date={pickedDay.date} />
                            )}
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  ))}
                </tbody>
              </table>
            </div>
          </Panel>
        </>
      )}
    </div>
  );
}
