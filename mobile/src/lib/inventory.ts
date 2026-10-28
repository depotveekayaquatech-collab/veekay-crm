/**
 * The employee's Inventory: their live stores grouped by vendor, with each vendor's contact numbers and how many of its stores have the month's
 * store card and bill. Pure functions (no React) so the rules are tested on their own.
 */
export interface InvStore {
  id: string;
  name: string;
  external_code: string;
  city: string | null;
  state: string | null;
  region_name: string | null;
  vendor_name: string | null;
  vendor_number?: string | null;
  poc_name?: string | null;
  poc_number?: string | null;
  today_marked?: boolean;
  today_count: number | null;
  pending_days?: number;
}

/** Which of the month's documents a store already has. Unknown (no entry in the map) is never counted as missing. */
export interface DocFlags { card: boolean; bill: boolean }

export type InvFilter = "all" | "card" | "bill" | "orders";

export interface VendorGroup {
  key: string;
  name: string;
  stores: InvStore[];
  /** The vendor's distinct phone numbers (one per line in the sheet, often two). */
  phones: string[];
  cards: number;
  bills: number;
}

export const NO_VENDOR = "No vendor";

export const vendorKeyOf = (name: string | null | undefined): string => (name ?? "").trim().replace(/\s+/g, " ").toLowerCase();

/** A store is "orders pending" until somebody has marked today. */
export const ordersPending = (s: InvStore): boolean => !(s.today_marked ?? s.today_count !== null);

export function matchesSearch(s: InvStore, needle: string): boolean {
  const n = needle.trim().toLowerCase();
  if (!n) return true;
  return [s.name, s.external_code, s.city, s.state, s.vendor_name, s.poc_name].some((x) => (x ?? "").toLowerCase().includes(n));
}

export function passesFilter(s: InvStore, docs: Map<string, DocFlags>, filter: InvFilter): boolean {
  if (filter === "all") return true;
  if (filter === "orders") return ordersPending(s);
  const d = docs.get(s.id);
  if (!d) return false;                                     // documents not loaded for this store: it cannot be called "missing"
  return filter === "card" ? !d.card : !d.bill;
}

/** The numbers on the filter chips: how many of `stores` each one would show. */
export function chipCounts(stores: InvStore[], docs: Map<string, DocFlags>): Record<InvFilter, number> {
  return {
    all: stores.length,
    card: stores.filter((s) => passesFilter(s, docs, "card")).length,
    bill: stores.filter((s) => passesFilter(s, docs, "bill")).length,
    orders: stores.filter(ordersPending).length,
  };
}

/** Distinct phone numbers of a set of stores, in the order met, ignoring blanks and repeats (spaces do not make a number different). */
export function phonesOf(stores: InvStore[]): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const s of stores) {
    for (const part of (s.vendor_number ?? "").split(/[\/,;]/)) {
      const p = part.trim();
      const key = p.replace(/[\s-]/g, "");
      if (key && !seen.has(key)) {
        seen.add(key);
        out.push(p);
      }
    }
  }
  return out;
}

/** Vendor groups A to Z (no-vendor last), each with its stores A to Z, contact numbers and document counts. */
export function groupByVendor(stores: InvStore[], docs: Map<string, DocFlags>): VendorGroup[] {
  const groups = new Map<string, VendorGroup>();
  for (const s of stores) {
    const key = vendorKeyOf(s.vendor_name);
    let g = groups.get(key);
    if (!g) {
      g = { key, name: key ? (s.vendor_name ?? "").trim().replace(/\s+/g, " ") : NO_VENDOR, stores: [], phones: [], cards: 0, bills: 0 };
      groups.set(key, g);
    }
    g.stores.push(s);
    const d = docs.get(s.id);
    if (d?.card) g.cards += 1;
    if (d?.bill) g.bills += 1;
  }
  const list = [...groups.values()];
  for (const g of list) {
    g.stores.sort((a, b) => a.name.localeCompare(b.name));
    g.phones = phonesOf(g.stores);
  }
  return list.sort((a, b) => (a.key === "" ? 1 : b.key === "" ? -1 : a.name.localeCompare(b.name)));
}

/** "3 days pending", "1 day pending", or "All up to date" for the banner on a store. */
export function pendingText(days: number | undefined): string {
  const d = days ?? 0;
  return d > 0 ? `${d} day${d === 1 ? "" : "s"} pending` : "All up to date";
}
