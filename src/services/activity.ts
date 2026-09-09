import { apiRequest } from "@/services/api";
import { mapPage, type Page, type PageWire } from "@/types/common";
import { toActivity, type Activity, type ActivityWire } from "@/types/activity";

interface ListParams {
  page?: number;
  pageSize?: number;
  entityType?: string;
}

export async function listActivity(params: ListParams = {}): Promise<Page<Activity>> {
  const qs = new URLSearchParams();
  if (params.page) qs.set("page", String(params.page));
  if (params.pageSize) qs.set("page_size", String(params.pageSize));
  if (params.entityType) qs.set("entity_type", params.entityType);
  const wire = await apiRequest<PageWire<ActivityWire>>(`/activity?${qs}`);
  return mapPage(wire, toActivity);
}
