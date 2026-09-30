import { apiRequest } from "@/services/api";
import { mapPage, type Page, type PageWire } from "@/types/common";
import {
  toStore,
  toSyncResult,
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

export async function importStoresFile(platform: string, file: File): Promise<StoreSyncResult> {
  const body = new FormData();
  body.append("platform", platform);
  body.append("file", file);
  const wire = await apiRequest<Parameters<typeof toSyncResult>[0]>("/stores/import", { method: "POST", body });
  return toSyncResult(wire);
}
