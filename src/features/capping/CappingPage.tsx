import { useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { Skeleton } from "@/components/feedback/Skeleton";
import { ErrorState } from "@/components/feedback/ErrorState";
import { EmptyState } from "@/components/feedback/EmptyState";
import { IconRefresh, IconSearch } from "@/components/ui/icons";
import { AverageCards } from "@/features/capping/AverageCards";
import { dateLabel, istToday } from "@/features/capping/helpers";
import { ReduceCappingBanner } from "@/features/capping/ReduceCappingBanner";
import { StoreCappingPanel } from "@/features/capping/StoreCappingPanel";
import { usePermission } from "@/hooks/usePermission";
import { getCappingAlert, getCappingList } from "@/services/capping";

const PAGE = 100;

/**
 * Zepto capping, kept to what matters: the alert on the collective averages, every live store with its latest capping and the day its entries started, a way to
 * set or remove a capping, and the record of every change. Pick a store to update it or to read its history.
 */
export function CappingPage() {
  const qc = useQueryClient();
  const canChange = usePermission("capping.change");
  const { data, isLoading, isError, error, refetch, isFetching } = useQuery({ queryKey: ["capping", "list"], queryFn: getCappingList, staleTime: 30_000 });
  // The "Reduce capping" alert: this month so far, all stores together.
  const today = istToday();
  const alert = useQuery({ queryKey: ["capping", "alert", today.slice(0, 7)], queryFn: () => getCappingAlert(`${today.slice(0, 7)}-01`, today), staleTime: 60_000 });
  const [needle, setNeedle] = useState("");
  const [missingOnly, setMissingOnly] = useState(false);
  const [picked, setPicked] = useState<string | null>(null);
  const [shown, setShown] = useState(PAGE);

  const rows = useMemo(() => {
    const n = needle.trim().toLowerCase();
    return (data?.rows ?? []).filter((r) => (!missingOnly || r.capping === null) && (!n || `${r.outletName} ${r.outletId} ${r.city ?? ""} ${r.state ?? ""}`.toLowerCase().includes(n)));
  }, [data, needle, missingOnly]);
  const selected = data?.rows.find((r) => r.storeId === picked) ?? null;

  return (
    <div className="flex flex-col gap-5">
      <PageHeader
        title="Zepto capping"
        subtitle={data ? `${data.total.toLocaleString("en-IN")} live stores · latest capping per day · ${data.withoutCapping.toLocaleString("en-IN")} with none` : "The latest capping of every live Zepto store."}
        action={
          <Button variant="secondary" onClick={() => { void qc.invalidateQueries({ queryKey: ["capping"] }); void refetch(); }} isLoading={isFetching && !isLoading}>
            <IconRefresh className="h-4 w-4" /> Refresh
          </Button>
        }
      />

      <ReduceCappingBanner alert={alert.data} />
      <AverageCards alert={alert.data} isLoading={alert.isLoading} error={alert.isError ? (alert.error as Error) : null} onRetry={() => void alert.refetch()} />

      {isLoading && <Skeleton className="h-64" />}
      {isError && <ErrorState message={error instanceof Error ? error.message : "Couldn't load the capping."} onRetry={() => refetch()} />}

      {data && (
        <div className="grid items-start gap-5 lg:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)]">
          <section className="min-w-0 rounded-xl border border-surface-border bg-surface shadow-card">
            <div className="flex flex-wrap items-center gap-2 border-b border-surface-border p-3">
              <div className="relative min-w-[12rem] flex-1">
                <IconSearch className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" aria-hidden="true" />
                <input
                  value={needle}
                  onChange={(e) => { setNeedle(e.target.value); setShown(PAGE); }}
                  placeholder="Search store, outlet ID or city"
                  aria-label="Search stores"
                  className="h-10 w-full rounded-lg border border-surface-border bg-surface pl-9 pr-3 text-sm shadow-sm outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20"
                />
              </div>
              <button
                type="button"
                aria-pressed={missingOnly}
                onClick={() => { setMissingOnly((v) => !v); setShown(PAGE); }}
                className={`h-10 rounded-lg px-3 text-sm font-semibold ring-1 ring-surface-border ${missingOnly ? "bg-brand-500 text-white" : "bg-surface text-gray-600 hover:bg-surface-subtle"}`}
              >
                No capping {data.withoutCapping.toLocaleString("en-IN")}
              </button>
            </div>
            {rows.length === 0 ? (
              <EmptyState title="No stores match" description="Try another search." />
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full min-w-[520px] text-sm">
                  <thead>
                    <tr className="bg-surface-subtle text-left text-[11px] font-bold uppercase tracking-wider text-gray-500">
                      <th className="px-4 py-2.5">Store</th><th className="px-3 py-2.5 text-right">Capping / day</th><th className="px-3 py-2.5">Entries started</th><th className="px-4 py-2.5" />
                    </tr>
                  </thead>
                  <tbody>
                    {rows.slice(0, shown).map((r) => (
                      <tr key={r.storeId} className={`cursor-pointer border-t border-surface-border/70 hover:bg-surface-subtle/70 ${picked === r.storeId ? "bg-brand-500/5" : ""}`} onClick={() => setPicked(r.storeId)}>
                        <td className="px-4 py-2.5">
                          <div className="font-medium text-gray-900">{r.outletName}</div>
                          <div className="text-xs text-gray-500">{r.outletId}{r.city ? ` · ${r.city}` : ""}</div>
                        </td>
                        <td className="px-3 py-2.5 text-right text-base font-extrabold tabular-nums text-heading">{r.capping ?? <Badge tone="neutral">None</Badge>}</td>
                        <td className="px-3 py-2.5 tabular-nums text-gray-600">{r.startDate ? dateLabel(r.startDate) : "—"}</td>
                        <td className="px-4 py-2.5 text-right text-xs font-semibold text-brand-600">{canChange ? "Update" : "History"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {rows.length > shown && (
                  <div className="border-t border-surface-border p-3 text-center">
                    <Button variant="secondary" size="sm" onClick={() => setShown((n) => n + PAGE)}>Show more ({(rows.length - shown).toLocaleString("en-IN")} left)</Button>
                  </div>
                )}
              </div>
            )}
          </section>

          <div className="min-w-0 lg:sticky lg:top-4">
            {selected ? (
              <StoreCappingPanel key={selected.storeId} row={selected} canChange={canChange} onClose={() => setPicked(null)} />
            ) : (
              <EmptyState title="Choose a store" description={canChange ? "Pick a store to set a new capping or read its history." : "Pick a store to read its capping history."} />
            )}
          </div>
        </div>
      )}
    </div>
  );
}
