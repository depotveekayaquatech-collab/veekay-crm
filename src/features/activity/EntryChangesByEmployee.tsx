import { Fragment, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Skeleton } from "@/components/feedback/Skeleton";
import { ErrorState } from "@/components/feedback/ErrorState";
import { EmptyState } from "@/components/feedback/EmptyState";
import { Panel, SearchBox, StatCard } from "@/features/orders/ui";
import { IconCheckCircle, IconUsers } from "@/components/ui/icons";
import { apiRequest } from "@/services/api";

interface EmployeeRow {
  employee_id: string | null; employee_code: string | null; employee_name: string | null; role_label: string | null; known: boolean;
  entries: number; unchanged: number; changed_once: number; changed_multiple: number; changes: number; changed_percent: number;
}
interface Summary {
  month: string; month_label: string; from: string; to: string;
  totals: { entries: number; unchanged: number; changed_once: number; changed_multiple: number; changes: number };
  employees: EmployeeRow[];
}
interface ChangedEntry {
  entry_id: string; order_date: string; store_name: string; store_code: string; first_count: number | null; count_now: number; changes: number;
  last_changed_by: string | null; last_changed_role: string | null; last_changed_at: string | null; status: string;
}
type Kind = "changed" | "once" | "multiple";

const shortDay = (iso: string) => new Date(`${iso}T00:00:00`).toLocaleDateString("en-IN", { day: "numeric", month: "short" });
const when = (iso: string | null) => (iso ? new Date(iso).toLocaleString("en-IN", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }) : "");

function shiftMonth(month: string, by: number): string {
  const [y, m] = month.split("-").map(Number);
  const d = new Date(y, m - 1 + by, 1);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

function ChangedEntries({ creatorId, month, kind }: { creatorId: string; month: string; kind: Kind }) {
  const q = useQuery({
    queryKey: ["entry-changes-of", creatorId, month, kind],
    queryFn: () => apiRequest<{ items: ChangedEntry[]; truncated: boolean }>(`/entries/changes-by-employee/${creatorId}?month=${month}&kind=${kind}`),
    staleTime: 0,
  });
  if (q.isLoading) return <Skeleton className="h-24" />;
  if (q.isError || !q.data) return <ErrorState message="Couldn't load these entries." onRetry={() => q.refetch()} />;
  if (q.data.items.length === 0) return <p className="text-sm text-gray-500">No entries here.</p>;
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[640px] text-sm">
        <thead>
          <tr className="text-left text-xs font-semibold uppercase tracking-wide text-gray-500">
            <th className="py-2 pr-3">Date</th><th className="py-2 pr-3">Store</th><th className="py-2 pr-3">First number</th><th className="py-2 pr-3">Now</th>
            <th className="py-2 pr-3">Changes</th><th className="py-2">Last changed by</th>
          </tr>
        </thead>
        <tbody>
          {q.data.items.map((i) => (
            <tr key={i.entry_id} className="border-t border-surface-border">
              <td className="py-2 pr-3 tabular-nums">{shortDay(i.order_date)}</td>
              <td className="py-2 pr-3"><span className="font-semibold text-gray-900">{i.store_name}</span> <span className="text-xs text-gray-500">{i.store_code}</span></td>
              <td className="py-2 pr-3 tabular-nums text-gray-500">{i.first_count ?? "–"}</td>
              <td className="py-2 pr-3 font-bold tabular-nums">{i.count_now}</td>
              <td className="py-2 pr-3"><Badge tone={i.changes >= 2 ? "danger" : "warning"}>{i.changes}x</Badge></td>
              <td className="py-2 text-xs text-gray-600">{i.last_changed_by ?? "–"}{i.last_changed_role ? ` (${i.last_changed_role})` : ""}{i.last_changed_at ? ` · ${when(i.last_changed_at)}` : ""}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {q.data.truncated && <p className="mt-2 text-xs text-gray-500">Showing the first 500.</p>}
    </div>
  );
}

/**
 * Audit log, second tab: for each person who entered numbers, how many of their entries (on the dates of the month) were never changed, changed once, or changed more
 * than once afterwards. Open a row to see those entries: the first number, the number now and who changed it last. Scoped by the server (a Team Lead sees their team).
 */
export function EntryChangesByEmployee() {
  const [month, setMonth] = useState("");                       // "" = the current month
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState<{ id: string; kind: Kind } | null>(null);
  const q = useQuery({
    queryKey: ["entry-changes-by-employee", month],
    queryFn: () => apiRequest<Summary>(`/entries/changes-by-employee${month ? `?month=${month}` : ""}`),
    staleTime: 0,
    refetchOnWindowFocus: true,
  });
  const d = q.data;
  const rows = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return (d?.employees ?? []).filter((e) => !needle || `${e.employee_name ?? ""} ${e.employee_code ?? ""}`.toLowerCase().includes(needle));
  }, [d, query]);
  const current = d?.month ?? month;
  const thisMonth = (() => { const n = new Date(); return `${n.getFullYear()}-${String(n.getMonth() + 1).padStart(2, "0")}`; })();

  const cell = (e: EmployeeRow, n: number, kind: Kind, tone: string) =>
    n > 0 && e.employee_id ? (
      <button type="button" onClick={() => setOpen(open?.id === e.employee_id && open.kind === kind ? null : { id: e.employee_id!, kind })}
        className={`rounded-md px-2 py-0.5 font-bold tabular-nums underline-offset-2 hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-brand-500 ${tone}`}>{n}</button>
    ) : <span className={`px-2 tabular-nums ${n > 0 ? tone : "text-gray-400"}`}>{n}</span>;

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-center gap-3">
        <p className="text-sm text-gray-600">Entries on the dates of the month, counted for the person who first entered them. Every change of a number counts once.</p>
        <div className="ml-auto flex items-center gap-1">
          <Button size="sm" variant="secondary" aria-label="Previous month" disabled={!current} onClick={() => { setMonth(shiftMonth(current, -1)); setOpen(null); }}>‹</Button>
          <span className="min-w-[8rem] text-center text-sm font-extrabold text-heading">{d?.month_label ?? "…"}</span>
          <Button size="sm" variant="secondary" aria-label="Next month" disabled={!current || current >= thisMonth} onClick={() => { setMonth(shiftMonth(current, 1)); setOpen(null); }}>›</Button>
        </div>
      </div>

      {q.isLoading && <Skeleton className="h-64 !rounded-2xl" />}
      {q.isError && <ErrorState message="Couldn't load the entries by employee." onRetry={() => q.refetch()} />}

      {d && (
        <>
          <div className="grid gap-4 sm:grid-cols-4">
            <StatCard label="Entries" value={d.totals.entries.toLocaleString()} tone="brand" icon={IconUsers} />
            <StatCard label="Never changed" value={d.totals.unchanged.toLocaleString()} tone="success" icon={IconCheckCircle} />
            <StatCard label="Changed once" value={d.totals.changed_once.toLocaleString()} tone="warning" icon={IconCheckCircle} />
            <StatCard label="Changed more than once" value={d.totals.changed_multiple.toLocaleString()} tone={d.totals.changed_multiple > 0 ? "warning" : "success"} icon={IconCheckCircle} />
          </div>

          <Panel
            flush
            title={<>Employees <span className="ml-1 font-medium text-gray-400">{rows.length}</span></>}
            subtitle="Most repeated changes first. Tap a number to see those entries."
            action={<SearchBox value={query} onChange={setQuery} placeholder="Search employee or code" className="w-full sm:w-64" />}
          >
            {rows.length === 0 ? (
              <div className="p-6"><EmptyState title="No entries for this month" /></div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full min-w-[720px] text-sm">
                  <thead>
                    <tr className="border-b border-surface-border bg-surface-subtle text-left text-xs font-semibold uppercase tracking-wide text-gray-500">
                      <th className="px-5 py-3">Employee</th><th className="px-3 py-3">Entries</th><th className="px-3 py-3">Never changed</th>
                      <th className="px-3 py-3">Changed once</th><th className="px-3 py-3">Changed more than once</th><th className="px-3 py-3">All changes</th><th className="px-3 py-3">Changed</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((e) => (
                      <Fragment key={e.employee_id ?? "unknown"}>
                        <tr className="border-b border-surface-border">
                          <td className="px-5 py-3">
                            <div className="font-semibold text-gray-900">{e.known ? (e.employee_name ?? "Unknown") : "Creator not recorded (older entries)"}</div>
                            {e.known && <div className="text-xs text-gray-500">{e.employee_code}{e.role_label ? ` · ${e.role_label}` : ""}</div>}
                          </td>
                          <td className="px-3 py-3 tabular-nums">{e.entries.toLocaleString()}</td>
                          <td className="px-3 py-3 tabular-nums text-status-success">{e.unchanged.toLocaleString()}</td>
                          <td className="px-3 py-3">{cell(e, e.changed_once, "once", "text-yellow-700 dark:text-yellow-300")}</td>
                          <td className="px-3 py-3">{cell(e, e.changed_multiple, "multiple", "text-status-danger")}</td>
                          <td className="px-3 py-3 tabular-nums">{e.changes.toLocaleString()}</td>
                          <td className="px-3 py-3 tabular-nums text-gray-600">{e.changed_percent}%</td>
                        </tr>
                        {open && open.id === e.employee_id && (
                          <tr className="border-b border-surface-border bg-surface-subtle/50">
                            <td colSpan={7} className="px-5 py-4">
                              <p className="mb-2 text-xs font-semibold text-gray-700">
                                {e.employee_name}: entries {open.kind === "once" ? "changed once" : "changed more than once"}
                              </p>
                              <ChangedEntries creatorId={open.id} month={d.month} kind={open.kind} />
                            </td>
                          </tr>
                        )}
                      </Fragment>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Panel>
        </>
      )}
    </div>
  );
}
