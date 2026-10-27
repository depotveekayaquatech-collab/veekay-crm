/**
 * The plain-text vendor report people paste to a vendor or into the office group:
 *
 *   Vendor name - Aqua Traders
 *   Store One (BLK-4821) - 120
 *   Store Two (BLK-4830) - 80
 *   Total bottles - 200         (only when the vendor has more than one store)
 *
 * Each store is its name and the platform's outlet ID, then its bottle count. A vendor with a single store is just its name and that store's line.
 */
export interface ReportStore {
  store_name: string;
  external_code?: string | null;
  bottles: number;
}

export interface ReportVendor {
  vendor_name: string | null;
  stores: ReportStore[];
  bottles: number;
}

const n = (v: number) => v.toLocaleString("en-IN");

/** One vendor's block. */
export function formatVendor(v: ReportVendor): string {
  const store = (s: ReportStore) => `${s.store_name}${s.external_code ? ` (${s.external_code})` : ""} - ${n(s.bottles)}`;
  const lines = [`Vendor name - ${v.vendor_name ?? "(No vendor name)"}`, ...v.stores.map(store)];
  if (v.stores.length > 1) lines.push(`Total bottles - ${n(v.bottles)}`);
  return lines.join("\n");
}

/** The whole message: a heading saying what and when, then a blank line between vendors. Empty when there is nothing to report. */
export function formatVendorReport(heading: string, vendors: ReportVendor[]): string {
  if (!vendors.length) return "";
  return [heading, "", vendors.map(formatVendor).join("\n\n")].join("\n");
}
