import { useMemo } from "react";
import { Button } from "@/components/ui/Button";
import { Skeleton } from "@/components/feedback/Skeleton";
import { IconDownload } from "@/components/ui/icons";
import { usePermission } from "@/hooks/usePermission";
import { downloadCsv } from "@/lib/csv";
import { summarizeByCity } from "@/lib/regionSummary";
import { useInventory } from "./useInventory";

const PLATFORM = "blinkit";
const REGIONS = ["North", "South"];

/** One table: Blinkit's North and South stores by state and city, with the number of vendors and stores in each. */
export function BlinkitRegionTable() {
  const isAdmin = usePermission("orders.correct");
  // An admin gets every platform from the server, so ask for Blinkit only; everyone else already sees just their own stores.
  const { data, isLoading, isError } = useInventory(isAdmin ? PLATFORM : "");
  const summary = useMemo(() => summarizeByCity(data?.items ?? [], { platformSlug: PLATFORM, regions: REGIONS }), [data]);

  if (isError || (!isLoading && summary.rows.length === 0)) return null;

  const regionTotal = (name: string) => summary.regions.find((r) => r.region === name);
  const csv = () =>
    downloadCsv(
      `blinkit-north-south-${new Date().toISOString().slice(0, 10)}.csv`,
      ["Region", "State", "City", "No. of vendors", "No. of stores"],
      [
        ...summary.rows.map((r) => [r.region, r.state, r.city, r.vendors, r.stores]),
        ...summary.regions.map((r) => [`${r.region} total`, "", "", r.vendors, r.stores]),
        ["Total", "", "", summary.total.vendors, summary.total.stores],
      ],
    );

  return (
    <section className="overflow-hidden rounded-xl border border-surface-border bg-surface shadow-card" aria-labelledby="blinkit-region-title">
      <div className="flex flex-wrap items-center gap-3 border-b border-surface-border/80 bg-surface-subtle px-5 py-3.5">
        <div className="min-w-0">
          <h2 id="blinkit-region-title" className="text-sm font-bold text-gray-900">Blinkit · North &amp; South</h2>
          <p className="text-xs text-gray-500">Vendors and stores in each city, by state.</p>
        </div>
        <Button variant="secondary" className="ml-auto" disabled={!summary.rows.length} onClick={csv}>
          <IconDownload className="h-4 w-4" />
          Export CSV
        </Button>
      </div>

      {isLoading ? (
        <Skeleton className="m-5 h-40" />
      ) : (
        <div className="max-h-[32rem] overflow-auto">
          <table className="w-full min-w-[560px] text-sm">
            <thead className="sticky top-0 z-10 bg-surface">
              <tr className="border-b border-surface-border text-left text-[11px] font-bold uppercase tracking-wider text-gray-500">
                <th className="px-5 py-2.5">Region</th>
                <th className="px-3 py-2.5">State</th>
                <th className="px-3 py-2.5">City</th>
                <th className="px-3 py-2.5 text-right">No. of vendors</th>
                <th className="px-5 py-2.5 text-right">No. of stores</th>
              </tr>
            </thead>
            <tbody>
              {summary.rows.map((r, i) => {
                const next = summary.rows[i + 1];
                const endOfRegion = !next || next.region !== r.region;
                const t = regionTotal(r.region);
                return [
                  <tr key={`${r.region}|${r.state}|${r.city}`} className="border-t border-surface-border/70">
                    <td className="px-5 py-2.5 font-medium text-gray-900">{r.region}</td>
                    <td className="px-3 py-2.5 text-gray-700">{r.state}</td>
                    <td className="px-3 py-2.5 text-gray-700">{r.city}</td>
                    <td className="px-3 py-2.5 text-right tabular-nums">{r.vendors}</td>
                    <td className="px-5 py-2.5 text-right tabular-nums">{r.stores}</td>
                  </tr>,
                  endOfRegion && t ? (
                    <tr key={`${r.region}-total`} className="border-t border-surface-border bg-surface-subtle font-bold text-gray-900">
                      <td className="px-5 py-2.5" colSpan={3}>{r.region} total</td>
                      <td className="px-3 py-2.5 text-right tabular-nums">{t.vendors}</td>
                      <td className="px-5 py-2.5 text-right tabular-nums">{t.stores}</td>
                    </tr>
                  ) : null,
                ];
              })}
            </tbody>
            <tfoot className="sticky bottom-0 bg-brand-50 font-bold text-gray-900">
              <tr className="border-t border-surface-border">
                <td className="px-5 py-3" colSpan={3}>All North &amp; South</td>
                <td className="px-3 py-3 text-right tabular-nums">{summary.total.vendors}</td>
                <td className="px-5 py-3 text-right tabular-nums">{summary.total.stores}</td>
              </tr>
            </tfoot>
          </table>
        </div>
      )}
    </section>
  );
}
