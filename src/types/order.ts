export interface MyStore {
  id: string;
  name: string;
  externalCode: string;
  /** The store's permanent system code (BKT000123 / ZPT000045). */
  crmCode: string;
  /** Another store of this platform has exactly this name: entries can be split between the two. */
  duplicateName: boolean;
  state: string | null;
  city: string | null;
  regionName: string | null;
  vendorName: string | null;
  vendorNumber: string | null;
  pocName: string | null;
  pocNumber: string | null;
  status: string;
  partnerSlug: string | null;
  partnerName: string | null;
  regionId: string | null;
  /** The server's "today" (YYYY-MM-DD) — quick entry marks against this, not the browser clock. */
  today: string;
  /** YOUR number for the day; null when you have not marked it, or somebody else did (their number is never shown to you). */
  todayCount: number | null;
  yesterdayCount: number | null;
  /** What happened to YOUR number after you entered it (who changed it, in which role, when, old -> new), or null. */
  todayChanged: DayChange | null;
  yesterdayChanged: DayChange | null;
  /** Somebody (you or a colleague) marked the day. */
  todayMarked: boolean;
  yesterdayMarked: boolean;
}

export interface CalendarDay {
  day: number;
  date: string;
  marked: boolean;
  count: number | null;
  source: "employee" | "admin" | null;
  /** Who wrote this day's number (an employee, or the admin / developer who imported or corrected it) and when. */
  enteredBy: string | null;
  enteredAt: string | null;
  isToday: boolean;
  isFuture: boolean;
  /** You entered this day's number. */
  mine: boolean;
  /** Marked by somebody at your own level: shown as marked, with no number, name or time. */
  masked: boolean;
  /** Entered by someone more senior (Team Lead, administrator, the developer): visible, read-only. */
  byHigher: boolean;
  /** Administrators only. */
  entryId: string | null;
  version: number | null;
  creatorName: string | null;
  creatorVerified: boolean | null;
  /** Where the entry stands: Submitted / Verified by Team Lead / Reviewed by Reviewer (a developer's hidden adjustment never names anyone). */
  verification: DayVerification | null;
  /** The latest change somebody made to the number after it was entered: who (name and role), when, and old -> new. */
  changed: DayChange | null;
}

export interface DayVerification {
  status: "submitted" | "verified_l2" | "reviewed_l3";
  label: string;
  byName: string | null;
  at: string | null;
}

export interface DayChange {
  byName: string | null;
  byRole: string | null;
  byRoleLabel: string;
  at: string;
  oldCount: number;
  newCount: number;
  reason: string | null;
}

export interface OrderCalendar {
  storeId: string;
  storeName: string;
  storeCode: string;
  regionName: string | null;
  year: number;
  month: number;
  monthLabel: string;
  days: CalendarDay[];
}

export interface MarkManyEntry {
  orderDate: string;
  bottleCount: number;
}

export interface MarkManyResultItem {
  orderDate: string;
  ok: boolean;
  error: string | null;
  /** "saved" | "already_saved" only when the SERVER confirmed the entry is stored. */
  status: string | null;
  entryId: string | null;
  savedAt: string | null;
  version: number | null;
}

export interface MarkManyResult {
  saved: number;
  failed: number;
  results: MarkManyResultItem[];
}

export interface EmployeeOverviewRow {
  employeeId: string;
  employeeCode: string;
  employeeName: string;
  regionName: string | null;
  totalStores: number;
  entriesDone: number;
  bottles: number;
  percent: number;
  error: string | null;
}

export interface SubmissionRow {
  id: string;
  submittedAt: string;
  employeeName: string | null;
  source: string;
  storeCode: string;
  storeName: string;
  orderDate: string;
  bottleCount: number;
}

export interface DailyOverview {
  partnerSlug: string;
  partnerLabel: string;
  date: string;
  dateLabel: string;
  dayOffset: number;
  employees: EmployeeOverviewRow[];
  recentSubmissions: SubmissionRow[];
}

export interface TrendPoint {
  date: string;
  label: string;
  entries: number;
  bottles: number;
}

export interface PlatformSummary {
  slug: string;
  label: string;
  totalStores: number;
  entriesDone: number;
  bottles: number;
  percent: number;
  employees: number;
  allStores: number;
  liveStores: number;
}

export interface LeaderRow {
  employeeName: string;
  regionName: string | null;
  entriesDone: number;
  totalStores: number;
  bottles: number;
  percent: number;
}

export interface CoverageRow {
  label: string;
  live: number;
  total: number;
}

export interface AttentionStore {
  id: string;
  name: string;
  externalCode: string;
  platform: string | null;
  status: string;
  city: string | null;
  state: string | null;
  regionName: string | null;
}

export interface DashboardInsights {
  trend: TrendPoint[];
  storeStatus: { LIVE: number; PENDING: number; CLOSE: number };
  platforms: PlatformSummary[];
  leaderboard: LeaderRow[];
  bottlesToday: number;
  bottlesYesterday: number;
  entriesToday: number;
  storesByRegion: CoverageRow[];
  storesByState: CoverageRow[];
  attentionStores: AttentionStore[];
  statusByPlatform: { slug: string; label: string; live: number; pending: number; close: number; total: number }[];
  /** Every (platform, region, state) that has stores — feeds the linked filter dropdowns. */
  scopes: { partnerSlug: string; region: string | null; state: string | null }[];
  dormantLive: number;
  dormantStores: AttentionStore[];
  lastStoreSync: string | null;
}

interface InsightsWire {
  trend: TrendPoint[];
  store_status: { LIVE: number; PENDING: number; CLOSE: number };
  platforms: {
    slug: string;
    label: string;
    total_stores: number;
    entries_done: number;
    bottles: number;
    percent: number;
    employees: number;
    all_stores: number;
    live_stores: number;
  }[];
  leaderboard: {
    employee_name: string;
    region_name: string | null;
    entries_done: number;
    total_stores: number;
    bottles: number;
    percent: number;
  }[];
  bottles_today: number;
  bottles_yesterday: number;
  entries_today: number;
  stores_by_region: CoverageRow[];
  stores_by_state: CoverageRow[];
  attention_stores: AttentionStoreWire[];
  status_by_platform: { slug: string; label: string; live: number; pending: number; close: number; total: number }[];
  scopes: { partner_slug: string; region: string | null; state: string | null }[];
  dormant_live: number;
  dormant_stores: AttentionStoreWire[];
  last_store_sync: string | null;
}

interface AttentionStoreWire {
  id: string;
  name: string;
  external_code: string;
  platform: string | null;
  status: string;
  city: string | null;
  state: string | null;
  region_name: string | null;
}

function mapAttention(a: AttentionStoreWire): AttentionStore {
  return {
    id: a.id,
    name: a.name,
    externalCode: a.external_code,
    platform: a.platform,
    status: a.status,
    city: a.city,
    state: a.state,
    regionName: a.region_name,
  };
}

export function toInsights(w: InsightsWire): DashboardInsights {
  return {
    trend: w.trend,
    storeStatus: w.store_status,
    platforms: w.platforms.map((p) => ({
      slug: p.slug,
      label: p.label,
      totalStores: p.total_stores,
      entriesDone: p.entries_done,
      bottles: p.bottles,
      percent: p.percent,
      employees: p.employees,
      allStores: p.all_stores,
      liveStores: p.live_stores,
    })),
    leaderboard: w.leaderboard.map((l) => ({
      employeeName: l.employee_name,
      regionName: l.region_name,
      entriesDone: l.entries_done,
      totalStores: l.total_stores,
      bottles: l.bottles,
      percent: l.percent,
    })),
    bottlesToday: w.bottles_today,
    bottlesYesterday: w.bottles_yesterday,
    entriesToday: w.entries_today,
    storesByRegion: w.stores_by_region,
    storesByState: w.stores_by_state,
    attentionStores: w.attention_stores.map(mapAttention),
    statusByPlatform: w.status_by_platform,
    scopes: w.scopes.map((x) => ({ partnerSlug: x.partner_slug, region: x.region, state: x.state })),
    dormantLive: w.dormant_live,
    dormantStores: w.dormant_stores.map(mapAttention),
    lastStoreSync: w.last_store_sync,
  };
}

/* ---- wire → app mappers ---- */

interface CalendarWire {
  store_id: string;
  store_name: string;
  store_code: string;
  region_name: string | null;
  year: number;
  month: number;
  month_label: string;
  days: {
    day: number;
    date: string;
    marked: boolean;
    count: number | null;
    source: "employee" | "admin" | null;
    entered_by?: string | null;
    entered_at?: string | null;
    is_today: boolean;
    is_future: boolean;
    mine?: boolean;
    masked?: boolean;
    by_higher?: boolean;
    entry_id?: string | null;
    version?: number | null;
    creator_name?: string | null;
    creator_verified?: boolean | null;
    verification?: { status: DayVerification["status"]; label: string; by_name: string | null; at: string | null } | null;
    changed?: DayChangeWire | null;
  }[];
}

export function toCalendar(w: CalendarWire): OrderCalendar {
  return {
    storeId: w.store_id,
    storeName: w.store_name,
    storeCode: w.store_code,
    regionName: w.region_name,
    year: w.year,
    month: w.month,
    monthLabel: w.month_label,
    days: w.days.map((d) => ({
      day: d.day,
      date: d.date,
      marked: d.marked,
      count: d.count,
      source: d.source,
      enteredBy: d.entered_by ?? null,
      enteredAt: d.entered_at ?? null,
      isToday: d.is_today,
      isFuture: d.is_future,
      mine: Boolean(d.mine),
      masked: Boolean(d.masked),
      byHigher: Boolean(d.by_higher),
      entryId: d.entry_id ?? null,
      version: d.version ?? null,
      creatorName: d.creator_name ?? null,
      creatorVerified: d.creator_verified ?? null,
      verification: d.verification ? { status: d.verification.status, label: d.verification.label, byName: d.verification.by_name, at: d.verification.at } : null,
      changed: toDayChange(d.changed),
    })),
  };
}

interface MyStoreWire {
  id: string;
  name: string;
  external_code: string;
  crm_code?: string | null;
  duplicate_name?: boolean;
  state: string | null;
  city: string | null;
  region_name: string | null;
  vendor_name: string | null;
  vendor_number: string | null;
  poc_name: string | null;
  poc_number: string | null;
  status: string;
  partner_slug: string | null;
  partner_name: string | null;
  region_id: string | null;
  today: string;
  today_count: number | null;
  yesterday_count: number | null;
  today_changed?: DayChangeWire | null;
  yesterday_changed?: DayChangeWire | null;
  today_marked?: boolean;
  yesterday_marked?: boolean;
}

type DayChangeWire = { by_name: string | null; by_role: string | null; by_role_label: string; at: string; old_count: number; new_count: number; reason: string | null };

const toDayChange = (c: DayChangeWire | null | undefined): DayChange | null =>
  c ? { byName: c.by_name, byRole: c.by_role, byRoleLabel: c.by_role_label, at: c.at, oldCount: c.old_count, newCount: c.new_count, reason: c.reason } : null;

export function toMyStore(w: MyStoreWire): MyStore {
  return {
    id: w.id,
    name: w.name,
    externalCode: w.external_code,
    crmCode: w.crm_code ?? "",
    duplicateName: Boolean(w.duplicate_name),
    state: w.state,
    city: w.city,
    regionName: w.region_name,
    vendorName: w.vendor_name,
    vendorNumber: w.vendor_number,
    pocName: w.poc_name,
    pocNumber: w.poc_number,
    status: w.status,
    partnerSlug: w.partner_slug,
    partnerName: w.partner_name,
    regionId: w.region_id,
    today: w.today,
    todayCount: w.today_count,
    yesterdayCount: w.yesterday_count,
    todayChanged: toDayChange(w.today_changed),
    yesterdayChanged: toDayChange(w.yesterday_changed),
    todayMarked: w.today_marked ?? w.today_count !== null,
    yesterdayMarked: w.yesterday_marked ?? w.yesterday_count !== null,
  };
}

interface OverviewWire {
  partner_slug: string;
  partner_label: string;
  date: string;
  date_label: string;
  day_offset: number;
  employees: {
    employee_id: string;
    employee_code: string;
    employee_name: string;
    region_name: string | null;
    total_stores: number;
    entries_done: number;
    bottles: number;
    percent: number;
    error: string | null;
  }[];
  recent_submissions: {
    id: string;
    submitted_at: string;
    employee_name: string | null;
    source: string;
    store_code: string;
    store_name: string;
    order_date: string;
    bottle_count: number;
  }[];
}

export function toOverview(w: OverviewWire): DailyOverview {
  return {
    partnerSlug: w.partner_slug,
    partnerLabel: w.partner_label,
    date: w.date,
    dateLabel: w.date_label,
    dayOffset: w.day_offset,
    employees: w.employees.map((e) => ({
      employeeId: e.employee_id,
      employeeCode: e.employee_code,
      employeeName: e.employee_name,
      regionName: e.region_name,
      totalStores: e.total_stores,
      entriesDone: e.entries_done,
      bottles: e.bottles,
      percent: e.percent,
      error: e.error,
    })),
    recentSubmissions: w.recent_submissions.map((s) => ({
      id: s.id,
      submittedAt: s.submitted_at,
      employeeName: s.employee_name,
      source: s.source,
      storeCode: s.store_code,
      storeName: s.store_name,
      orderDate: s.order_date,
      bottleCount: s.bottle_count,
    })),
  };
}

export interface OrderImportResult {
  platform: string;
  sheets: string[];
  rowsRead: number;
  created: number;
  updated: number;
  unchanged: number;
  keptExisting: number;
  unknownStores: number;
  invalidValues: number;
  futureSkipped: number;
  startDatesSet: number;
  vendorStartsSet: number;
  warnings: string[];
}

export function toOrderImportResult(w: {
  platform: string;
  sheets: string[];
  rows_read: number;
  created: number;
  updated: number;
  unchanged: number;
  kept_existing: number;
  unknown_stores: number;
  invalid_values: number;
  future_skipped: number;
  start_dates_set?: number;
  vendor_starts_set?: number;
  warnings: string[];
}): OrderImportResult {
  return {
    platform: w.platform,
    sheets: w.sheets,
    rowsRead: w.rows_read,
    created: w.created,
    updated: w.updated,
    unchanged: w.unchanged,
    keptExisting: w.kept_existing,
    unknownStores: w.unknown_stores,
    invalidValues: w.invalid_values,
    futureSkipped: w.future_skipped,
    startDatesSet: w.start_dates_set ?? 0,
    vendorStartsSet: w.vendor_starts_set ?? 0,
    warnings: w.warnings,
  };
}
