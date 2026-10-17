import { useQuery } from "@tanstack/react-query";
import { getStoreVendors } from "@/services/stores";

const day = (d: string | null) =>
  d ? new Date(`${d}T00:00:00`).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" }) : "unknown";
const stamp = (iso: string | null) => (iso ? new Date(iso).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" }) : "");

const HOW: Record<string, string> = { manual: "edited by hand", file: "file import", sheet: "sheet sync" };

function whoChanged(changedBy: string | null, source: string, recordedOn: string | null) {
  if (source === "backfill" || (!changedBy && !HOW[source])) return "Existing record";
  const how = HOW[source] ?? source;
  return `${changedBy ? `Changed by ${changedBy}` : "Changed"} · ${how}${recordedOn ? ` · ${stamp(recordedOn)}` : ""}`;
}

/** Every vendor a store has had, newest first, with the dates and who made each change. */
export function VendorHistory({ storeId, minEntries = 2 }: { storeId: string; minEntries?: number }) {
  const { data = [], isLoading } = useQuery({ queryKey: ["store-vendors", storeId], queryFn: () => getStoreVendors(storeId) });
  if (isLoading || data.length < minEntries) return null; // nothing worth showing until enough vendors exist
  return (
    <div className="sm:col-span-2">
      <p className="mb-1 text-xs font-bold uppercase tracking-wider text-gray-500">Vendor history</p>
      <ul className="flex flex-col divide-y divide-surface-border rounded-lg border border-surface-border text-sm">
        {data.map((v, i) => (
          <li key={i} className="flex flex-col gap-0.5 px-3 py-2">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="font-medium text-gray-900">
                {v.vendorName}
                {v.vendorNumber ? <span className="ml-2 font-normal text-gray-500">{v.vendorNumber}</span> : null}
              </span>
              <span className="text-xs text-gray-500">
                {v.current ? "Current · since " : ""}
                {day(v.startDate)}
                {v.current ? "" : ` to ${day(v.endDate)}`}
                {!v.startConfirmed ? " (start provisional)" : ""}
              </span>
            </div>
            <span className="text-xs text-gray-400">{whoChanged(v.changedBy, v.source, v.recordedOn)}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
