import { apiRequest } from "@/services/api";
import { mapPage, type Page, type PageWire } from "@/types/common";
import {
  toStore,
  toSyncResult,
  toVendorPeriod,
  type VendorPeriod,
  type Store,
  type StoreInput,
  type StoreSyncResult,
  type StoreWire,
} from "@/types/store";

interface ListParams {
  page?: number;
  pageSize?: number;
  regionId?: string;
  partner?: string;
  state?: string;
  storeStatus?: string;
  search?: string;
}

export async function listStores(params: ListParams = {}): Promise<Page<Store>> {
  const qs = new URLSearchParams();
  if (params.page) qs.set("page", String(params.page));
  if (params.pageSize) qs.set("page_size", String(params.pageSize));
  if (params.regionId) qs.set("region_id", params.regionId);
  if (params.partner) qs.set("partner", params.partner);
  if (params.state) qs.set("state", params.state);
  if (params.storeStatus) qs.set("store_status", params.storeStatus);
  if (params.search) qs.set("search", params.search);
  const wire = await apiRequest<PageWire<StoreWire>>(`/stores?${qs}`);
  return mapPage(wire, toStore);
}

/** Every store in a single request (the server builds and shares it) instead of walking 16 pages. */
export async function listAllStores(): Promise<Store[]> {
  return (await apiRequest<StoreWire[]>("/stores/all")).map(toStore);
}

export async function createStore(input: StoreInput): Promise<Store> {
  return toStore(await apiRequest<StoreWire>("/stores", { method: "POST", body: input }));
}

export async function updateStore(id: string, input: Partial<StoreInput>): Promise<Store> {
  return toStore(await apiRequest<StoreWire>(`/stores/${id}`, { method: "PATCH", body: input }));
}

export async function closeStore(id: string): Promise<Store> {
  return toStore(await apiRequest<StoreWire>(`/stores/${id}`, { method: "DELETE" }));
}

export interface DeleteClosedResult {
  dryRun: boolean;
  closed: number;
  deletableCount: number;
  keptWithOrders: number;
  keptWithOtherRecords: number;
  deleted: number;
  deletable: { id: string; name: string; externalCode: string; platform: string }[];
}

/** Delete Closed stores that hold no history at all (no orders, documents, tickets or cash purchases). `dryRun` only reports. */
export async function deleteClosedStores(opts: { platform?: string; storeIds?: string[]; dryRun: boolean }): Promise<DeleteClosedResult> {
  const w = await apiRequest<{
    dry_run: boolean; closed: number; deletable_count: number; kept_with_orders: number; kept_with_other_records: number; deleted: number;
    deletable: { id: string; name: string; external_code: string; platform: string }[];
  }>("/stores/delete-closed", { method: "POST", body: { platform: opts.platform || null, store_ids: opts.storeIds ?? null, dry_run: opts.dryRun } });
  return {
    dryRun: w.dry_run, closed: w.closed, deletableCount: w.deletable_count, keptWithOrders: w.kept_with_orders,
    keptWithOtherRecords: w.kept_with_other_records, deleted: w.deleted,
    deletable: w.deletable.map((d) => ({ id: d.id, name: d.name, externalCode: d.external_code, platform: d.platform })),
  };
}

export async function syncStores(platform?: string): Promise<StoreSyncResult[]> {
  const qs = platform ? `?platform=${encodeURIComponent(platform)}` : "";
  const wire = await apiRequest<Parameters<typeof toSyncResult>[0][]>(`/stores/sync${qs}`, {
    method: "POST",
  });
  return wire.map(toSyncResult);
}

export async function importStoresFile(platform: string, file: File, allowMismatch = false): Promise<StoreSyncResult> {
  const body = new FormData();
  body.append("platform", platform);
  if (allowMismatch) body.append("allow_mismatch", "true");
  body.append("file", file);
  const wire = await apiRequest<Parameters<typeof toSyncResult>[0]>("/stores/import", {
    method: "POST",
    body,
    networkErrorMessage:
      "The connection to the server was lost while it was processing the file. Your internet may be fine: the server " +
      "may have restarted. Nothing was imported. It is safe to try again, or split the file into smaller parts.",
  });
  return toSyncResult(wire);
}

export interface DeleteAllStoresResult {
  platform: string;
  storesDeleted: number;
  orderEntriesDeleted: number;
}

/** Wipe every store (and its order history) of one platform, or of all when `platform` is empty. */
export async function deleteAllStores(platform: string, confirm: string): Promise<DeleteAllStoresResult> {
  const qs = new URLSearchParams({ confirm });
  if (platform) qs.set("platform", platform);
  const w = await apiRequest<{ platform: string; stores_deleted: number; order_entries_deleted: number }>(
    `/stores?${qs}`,
    { method: "DELETE" },
  );
  return { platform: w.platform, storesDeleted: w.stores_deleted, orderEntriesDeleted: w.order_entries_deleted };
}

export interface MovePlatformResult {
  from: string;
  to: string;
  matched: number;
  moved: number;
  skippedDuplicates: number;
  dryRun: boolean;
}

/** Re-file stores imported under the wrong platform (developer only). `dryRun` only counts. */
export async function movePlatform(
  fromPlatform: string,
  toPlatform: string,
  contains: string,
  dryRun: boolean,
): Promise<MovePlatformResult> {
  const w = await apiRequest<{ from: string; to: string; matched: number; moved: number; skipped_duplicates: number; dry_run: boolean }>(
    "/stores/move-platform",
    { method: "POST", body: { from_platform: fromPlatform, to_platform: toPlatform, contains, dry_run: dryRun } },
  );
  return { from: w.from, to: w.to, matched: w.matched, moved: w.moved, skippedDuplicates: w.skipped_duplicates, dryRun: w.dry_run };
}

export interface StartDatesResult {
  stores: number;
  toFill: number;       // empty start dates that can be filled
  moveEarlier: number;  // the date is later than the first supply: moves back to it (always applied)
  keepHandDates: number; // the date is earlier than the first supply (typed by hand): kept unless replacing
  unchanged: number;    // already equals the first supply
  noOrders: number;     // no supplied day in the order sheet yet: left alone
  toChange: number;     // what this run changes (fills, plus replacements when `replaceExisting`)
  replaceExisting: boolean;
  dryRun: boolean;
  noOrdersByStatus: Record<string, number>;
  noOrdersLiveSample: { name: string; code: string; platform: string }[];
}

/** Developer only: set each store's start date to its first supplied day from the order sheet. `dryRun` only counts. */
export async function syncStartDates(platform: string, replaceExisting: boolean, dryRun: boolean, vendor = ""): Promise<StartDatesResult> {
  const w = await apiRequest<{
    stores: number; to_fill: number; move_earlier: number; keep_hand_dates: number; unchanged: number; no_orders: number; to_change: number;
    replace_existing: boolean; dry_run: boolean; no_orders_by_status?: Record<string, number>;
    no_orders_live_sample?: { name: string; code: string; platform: string }[];
  }>("/stores/sync-start-dates", { method: "POST", body: { platform: platform || null, overwrite: replaceExisting, dry_run: dryRun, vendor: vendor.trim() || null } });
  return {
    stores: w.stores, toFill: w.to_fill, moveEarlier: w.move_earlier, keepHandDates: w.keep_hand_dates, unchanged: w.unchanged, noOrders: w.no_orders,
    toChange: w.to_change, replaceExisting: w.replace_existing, dryRun: w.dry_run,
    noOrdersByStatus: w.no_orders_by_status ?? {}, noOrdersLiveSample: w.no_orders_live_sample ?? [],
  };
}

/** Every vendor that has supplied a store (newest first); the current vendor has no end date. */
export async function getStoreVendors(id: string): Promise<VendorPeriod[]> {
  const rows = await apiRequest<Parameters<typeof toVendorPeriod>[0][]>(`/stores/${id}/vendors`);
  return rows.map(toVendorPeriod);
}

export interface DuplicateStore {
  store: Store;
  orderDays: number;
  createdAt: string;
}

export interface DuplicateGroup {
  kind: "name" | "id";
  label: string;
  platform: string | null;
  stores: DuplicateStore[];
}

export interface DuplicateReport {
  totalGroups: number;
  totalStores: number;
  groups: DuplicateGroup[];
}

/** Stores that exist more than once: the same name on a platform, or the same Outlet ID ignoring capitals, spaces and dashes. */
export async function listDuplicateStores(): Promise<DuplicateReport> {
  const w = await apiRequest<{
    total_groups: number;
    total_stores: number;
    groups: { kind: "name" | "id"; label: string; platform: string | null; stores: (StoreWire & { order_days: number; created_at: string })[] }[];
  }>("/stores/duplicates");
  return {
    totalGroups: w.total_groups,
    totalStores: w.total_stores,
    groups: w.groups.map((g) => ({
      kind: g.kind,
      label: g.label,
      platform: g.platform,
      stores: g.stores.map((s) => ({ store: toStore(s), orderDays: s.order_days, createdAt: s.created_at })),
    })),
  };
}

export interface MergeSuggestion {
  name: string;
  oldCode: string;
  newCode: string;
  oldOrderDays: number;
  newOrderDays: number;
}

/** Stores of a platform that exist twice under two Outlet IDs with the same name (developer only). */
export async function mergeSuggestions(platform: string): Promise<MergeSuggestion[]> {
  const w = await apiRequest<{ name: string; old_code: string; new_code: string; old_order_days: number; new_order_days: number }[]>(
    `/stores/merge-suggestions?platform=${encodeURIComponent(platform)}`,
  );
  return w.map((r) => ({ name: r.name, oldCode: r.old_code, newCode: r.new_code, oldOrderDays: r.old_order_days, newOrderDays: r.new_order_days }));
}

export interface MergeRow {
  oldCode: string;
  newCode: string;
  name: string | null;
  ok: boolean;
  reason: string | null;
  moved: Record<string, number>;
}

export interface MergeResult {
  platform: string;
  dryRun: boolean;
  merged: number;
  skipped: number;
  results: MergeRow[];
}

/** Move everything a temporary-ID store holds onto the store with the real Outlet ID, then remove it (developer only). */
export interface MergePairInput {
  oldCode: string;
  newCode: string;
  /** Exact store ids; needed when several stores share an Outlet ID. */
  oldId?: string;
  newId?: string;
}

export async function mergeStores(platform: string, pairs: MergePairInput[], dryRun: boolean): Promise<MergeResult> {
  const w = await apiRequest<{
    platform: string;
    dry_run: boolean;
    merged: number;
    skipped: number;
    results: { old_code: string; new_code: string; name: string | null; ok: boolean; reason: string | null; moved: Record<string, number> }[];
  }>("/stores/merge", {
    method: "POST",
    body: { platform, dry_run: dryRun, pairs: pairs.map((p) => ({ old_code: p.oldCode, new_code: p.newCode, old_id: p.oldId, new_id: p.newId })) },
  });
  return {
    platform: w.platform,
    dryRun: w.dry_run,
    merged: w.merged,
    skipped: w.skipped,
    results: w.results.map((r) => ({ oldCode: r.old_code, newCode: r.new_code, name: r.name, ok: r.ok, reason: r.reason, moved: r.moved })),
  };
}

export interface PlatformCheckRow {
  store: Store;
  platform: string | null;
  orderDays: number;
  hasCapping: boolean;
  reasons: string[];
  suggestedPlatform: string | null;
}

/** Stores that look filed under the wrong platform, with the evidence. Nothing is moved by this call. */
export async function listPlatformCheck(): Promise<{ total: number; stores: PlatformCheckRow[] }> {
  const w = await apiRequest<{
    total: number;
    stores: { store: StoreWire; platform: string | null; order_days: number; has_capping: boolean; reasons: string[]; suggested_platform: string | null }[];
  }>("/stores/platform-check");
  return {
    total: w.total,
    stores: w.stores.map((r) => ({
      store: toStore(r.store), platform: r.platform, orderDays: r.order_days, hasCapping: r.has_capping, reasons: r.reasons, suggestedPlatform: r.suggested_platform,
    })),
  };
}

/** Move ONE store to another platform (its orders and history go with it; a Zepto capping number stays only on Zepto). */
export async function moveStoreToPlatform(storeId: string, toPlatform: string): Promise<{ name: string; platform: string; cappingRemoved: number }> {
  const w = await apiRequest<{ name: string; platform: string; capping_removed: number }>(`/stores/${storeId}/move-platform`, {
    method: "POST",
    body: { to_platform: toPlatform },
  });
  return { name: w.name, platform: w.platform, cappingRemoved: w.capping_removed };
}

export interface ImportIssue {
  row: number;
  name: string | null;
  code: string | null;
  reason: string;
  detail: string;
  crmStores: { id: string; externalCode: string; status: string }[];
}

export interface ImportIssueRun {
  platform: string;
  platformSlug: string;
  at: string;
  source: string | null;
  rowsRead: number | null;
  created: number | null;
  updated: number | null;
  issueCount: number;
  issues: ImportIssue[];
}

/** The rows each platform's latest store upload could not use, for someone to sort out. */
export async function listImportIssues(): Promise<{ totalIssues: number; runs: ImportIssueRun[] }> {
  const w = await apiRequest<{
    total_issues: number;
    runs: {
      platform: string; platform_slug: string; at: string; source: string | null; rows_read: number | null; created: number | null;
      updated: number | null; issue_count: number;
      issues: { row: number; name: string | null; code: string | null; reason: string; detail: string; crm_stores: { id: string; external_code: string; status: string }[] }[];
    }[];
  }>("/stores/import-issues");
  return {
    totalIssues: w.total_issues,
    runs: w.runs.map((r) => ({
      platform: r.platform, platformSlug: r.platform_slug, at: r.at, source: r.source, rowsRead: r.rows_read, created: r.created,
      updated: r.updated, issueCount: r.issue_count,
      issues: r.issues.map((i) => ({
        row: i.row, name: i.name, code: i.code, reason: i.reason, detail: i.detail,
        crmStores: (i.crm_stores ?? []).map((c) => ({ id: c.id, externalCode: c.external_code, status: c.status })),
      })),
    })),
  };
}
