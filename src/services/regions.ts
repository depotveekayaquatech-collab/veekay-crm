import { apiRequest } from "@/services/api";
import { mapPage, type Page, type PageWire } from "@/types/common";
import { toRegion, type Region, type RegionInput, type RegionWire } from "@/types/region";

interface ListParams {
  page?: number;
  pageSize?: number;
}

export async function listRegions(params: ListParams = {}): Promise<Page<Region>> {
  const qs = new URLSearchParams();
  if (params.page) qs.set("page", String(params.page));
  if (params.pageSize) qs.set("page_size", String(params.pageSize));
  const wire = await apiRequest<PageWire<RegionWire>>(`/regions?${qs}`);
  return mapPage(wire, toRegion);
}

export async function createRegion(input: RegionInput): Promise<Region> {
  return toRegion(await apiRequest<RegionWire>("/regions", { method: "POST", body: input }));
}

export async function updateRegion(id: string, input: Partial<RegionInput> & { is_active?: boolean }): Promise<Region> {
  return toRegion(await apiRequest<RegionWire>(`/regions/${id}`, { method: "PATCH", body: input }));
}

export async function deactivateRegion(id: string): Promise<void> {
  await apiRequest(`/regions/${id}`, { method: "DELETE" });
}
