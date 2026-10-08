/* Wire shapes (snake_case) + app shapes (camelCase) for Reports & Pending. */

export type ReportGroup = "region" | "partner" | "state" | "store";

export interface ReportRow {
  key: string;
  label: string;
  sub: string | null;
  entries: number;
  bottles: number;
  activeDays: number;
  avgPerEntry: number;
  sharePercent: number;
}

export interface ReportPoint {
  date: string;
  label: string;
  bottles: number;
  entries: number;
}

export interface SalesReport {
  start: string;
  end: string;
  groupBy: ReportGroup;
  totalBottles: number;
  totalEntries: number;
  days: number;
  avgBottlesPerDay: number;
  rows: ReportRow[];
  /** Breakdown rows before any `limit` trimmed them (e.g. how many stores had orders). */
  rowCount: number;
  series: ReportPoint[];
}

export interface PendingStore {
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
  pendingDays: number;
  lastEntryDate: string | null;
}

export interface PendingEntries {
  date: string;
  dateLabel: string;
  dayOffset: number;
  liveStores: number;
  marked: number;
  pending: number;
  items: PendingStore[];
}

/* eslint-disable @typescript-eslint/no-explicit-any */
export function toReport(w: any): SalesReport {
  return {
    start: w.start,
    end: w.end,
    groupBy: w.group_by,
    totalBottles: w.total_bottles,
    totalEntries: w.total_entries,
    days: w.days,
    avgBottlesPerDay: w.avg_bottles_per_day,
    rowCount: w.row_count ?? w.rows.length,
    rows: w.rows.map((r: any) => ({
      key: r.key,
      label: r.label,
      sub: r.sub,
      entries: r.entries,
      bottles: r.bottles,
      activeDays: r.active_days,
      avgPerEntry: r.avg_per_entry,
      sharePercent: r.share_percent,
    })),
    series: w.series,
  };
}

export function toPending(w: any): PendingEntries {
  return {
    date: w.date,
    dateLabel: w.date_label,
    dayOffset: w.day_offset,
    liveStores: w.live_stores,
    marked: w.marked,
    pending: w.pending,
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
      pendingDays: s.pending_days ?? 0,
      lastEntryDate: s.last_entry_date ?? null,
    })),
  };
}
