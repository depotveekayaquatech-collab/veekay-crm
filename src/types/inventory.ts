export interface InventoryStore {
  id: string;
  name: string;
  externalCode: string;
  platform: string | null;
  platformSlug: string | null;
  regionName: string | null;
  state: string | null;
  city: string | null;
  vendorName: string | null;
  vendorNumber: string | null;
  pocName: string | null;
  pocNumber: string | null;
  startDate: string | null;
  lastEntryDate: string | null;
  pendingDays: number;
  markedToday: boolean;
  monthBottles: number;
  monthEntries: number;
}

export interface Inventory {
  monthLabel: string;
  summary: { stores: number; behind: number; markedToday: number; totalPendingDays: number };
  items: InventoryStore[];
}

/* eslint-disable @typescript-eslint/no-explicit-any */
export function toInventory(w: any): Inventory {
  return {
    monthLabel: w.month_label,
    summary: {
      stores: w.summary.stores,
      behind: w.summary.behind,
      markedToday: w.summary.marked_today,
      totalPendingDays: w.summary.total_pending_days,
    },
    items: w.items.map((s: any) => ({
      id: s.id,
      name: s.name,
      externalCode: s.external_code,
      platform: s.platform,
      platformSlug: s.platform_slug,
      regionName: s.region_name,
      state: s.state,
      city: s.city,
      vendorName: s.vendor_name,
      vendorNumber: s.vendor_number,
      pocName: s.poc_name,
      pocNumber: s.poc_number,
      startDate: s.start_date ?? null,
      lastEntryDate: s.last_entry_date,
      pendingDays: s.pending_days,
      markedToday: s.marked_today,
      monthBottles: s.month_bottles,
      monthEntries: s.month_entries,
    })),
  };
}
