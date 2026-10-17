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
  differs: number;      // a date is set but isn't the first supply
  unchanged: number;    // already equals the first supply
  noOrders: number;     // no supplied day in the order sheet yet: left alone
  toChange: number;     // what this run changes (fills, plus replacements when `replaceExisting`)
  replaceExisting: boolean;
  dryRun: boolean;
}

/** Developer only: set each store's start date to its first supplied day from the order sheet. `dryRun` only counts. */
export async function syncStartDates(platform: string, replaceExisting: boolean, dryRun: boolean): Promise<StartDatesResult> {
  const w = await apiRequest<{
    stores: number; to_fill: number; differs: number; unchanged: number; no_orders: number; to_change: number;
    replace_existing: boolean; dry_run: boolean;
  }>("/stores/sync-start-dates", { method: "POST", body: { platform: platform || null, overwrite: replaceExisting, dry_run: dryRun } });
  return {
    stores: w.stores, toFill: w.to_fill, differs: w.differs, unchanged: w.unchanged, noOrders: w.no_orders,
    toChange: w.to_change, replaceExisting: w.replace_existing, dryRun: w.dry_run,
  };
}

/** Every vendor that has supplied a store (newest first); the current vendor has no end date. */
export async function getStoreVendors(id: string): Promise<VendorPeriod[]> {
  const rows = await apiRequest<Parameters<typeof toVendorPeriod>[0][]>(`/stores/${id}/vendors`);
  return rows.map(toVendorPeriod);
}
