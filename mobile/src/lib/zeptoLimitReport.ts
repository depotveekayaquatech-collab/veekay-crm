/**
 * The plain-text Zepto vendor message people paste into a vendor's WhatsApp chat (the same text the web app builds):
 *
 *   Zepto - Vendor limit, October 2026 (as on 29 Oct)
 *
 *   Vendor name - Aqua Traders
 *
 *   Store - Store One (ZPT-4821)
 *   Monthly limit - 900            (the store's capping x 30, the number the Capping page measures against)
 *   Supplied till date - 450       (every bottle marked at the store this month so far)
 *   Pending limit - 450            (limit - supplied; 0 and "(over by N)" once it is used up)
 *
 * Sent again a few days later, the pending limit is what the vendor may still supply. A store with no capping has no limit, so it shows only what was supplied.
 */
export interface LimitStore {
  store_name: string;
  external_code?: string | null;
  /** daily capping x 30; null when the store has no capping. */
  monthly_limit: number | null;
  /** Bottles supplied this month so far. */
  bottles: number;
  /** limit - everything supplied, never below 0; null when there is no limit. */
  pending: number | null;
  over_by?: number | null;
}

export interface LimitVendor {
  vendor_name: string | null;
  stores: LimitStore[];
}

const n = (v: number) => v.toLocaleString("en-IN");
export const NO_VENDOR = "(No vendor name)";

/** One store's three lines (four with its name). */
export function formatLimitStore(s: LimitStore): string {
  const head = `Store - ${s.store_name}${s.external_code ? ` (${s.external_code})` : ""}`;
  if (s.monthly_limit === null || s.pending === null) return [head, "Monthly limit - No capping set", `Supplied till date - ${n(s.bottles)}`].join("\n");
  const over = (s.over_by ?? 0) > 0 ? ` (over by ${n(s.over_by ?? 0)})` : "";
  return [head, `Monthly limit - ${n(s.monthly_limit)}`, `Supplied till date - ${n(s.bottles)}`, `Pending limit - ${n(s.pending)}${over}`].join("\n");
}

/** One vendor's block: its name, then each store. With several stores that have a limit, a closing total of the limit, what was supplied and what is pending. */
export function formatLimitVendor(v: LimitVendor): string {
  const blocks = [`Vendor name - ${v.vendor_name ?? NO_VENDOR}`, ...v.stores.map(formatLimitStore)];
  const capped = v.stores.filter((s) => s.monthly_limit !== null && s.pending !== null);
  if (capped.length > 1) {
    const sum = (f: (s: LimitStore) => number) => capped.reduce((t, s) => t + f(s), 0);
    blocks.push([`Total of ${capped.length} stores`, `Monthly limit - ${n(sum((s) => s.monthly_limit ?? 0))}`, `Supplied till date - ${n(sum((s) => s.bottles))}`, `Pending limit - ${n(sum((s) => s.pending ?? 0))}`].join("\n"));
  }
  return blocks.join("\n\n");
}

/** The whole message: a heading saying what and when, then a blank line between vendors. Empty when there is nothing to report. */
export function formatLimitReport(heading: string, vendors: LimitVendor[]): string {
  if (!vendors.length) return "";
  return [heading, "", vendors.map(formatLimitVendor).join("\n\n\n")].join("\n");
}

/** Stores grouped by vendor (spelling and spacing ignored), vendors A to Z, stores by name; the vendor-less last. For a list that is one row per store. */
export function groupByVendor<T extends LimitStore & { vendor_name: string | null }>(rows: T[]): LimitVendor[] {
  const groups = new Map<string, LimitVendor>();
  for (const r of rows) {
    const name = r.vendor_name?.trim().replace(/\s+/g, " ") || null;
    const key = (name ?? "").toLowerCase();
    const g = groups.get(key) ?? { vendor_name: name, stores: [] };
    g.stores.push(r);
    groups.set(key, g);
  }
  const out = [...groups.values()];
  for (const g of out) g.stores.sort((a, b) => a.store_name.localeCompare(b.store_name));
  return out.sort((a, b) => (a.vendor_name === null ? 1 : 0) - (b.vendor_name === null ? 1 : 0) || (a.vendor_name ?? "").toLowerCase().localeCompare((b.vendor_name ?? "").toLowerCase()));
}
