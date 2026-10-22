import { apiRequest } from "@/services/api";
import {
  toCalendar,
  toInsights,
  toMyStore,
  toOrderImportResult,
  toOverview,
  type DashboardInsights,
  type DailyOverview,
  type MarkManyEntry,
  type MarkManyResult,
  type MyStore,
  type OrderCalendar,
  type OrderImportResult,
} from "@/types/order";

export async function getMyStores(): Promise<MyStore[]> {
  const rows = await apiRequest<Parameters<typeof toMyStore>[0][]>("/orders/my-stores");
  return rows.map(toMyStore);
}

export async function getCalendar(storeId: string, year?: number, month?: number): Promise<OrderCalendar> {
  const qs = new URLSearchParams({ store_id: storeId });
  if (year) qs.set("year", String(year));
  if (month) qs.set("month", String(month));
  return toCalendar(await apiRequest(`/orders/calendar?${qs}`));
}

export async function markOrder(
  storeId: string,
  orderDate: string,
  bottleCount: number,
): Promise<OrderCalendar> {
  return toCalendar(
    await apiRequest("/orders/mark", {
      method: "POST",
      body: { store_id: storeId, order_date: orderDate, bottle_count: bottleCount },
    }),
  );
}

export async function markManyOrders(
  storeId: string,
  entries: MarkManyEntry[],
): Promise<MarkManyResult> {
  const wire = await apiRequest<{
    saved: number;
    failed: number;
    results: { order_date: string; ok: boolean; error: string | null }[];
  }>("/orders/mark-many", {
    method: "POST",
    body: {
      store_id: storeId,
      entries: entries.map((e) => ({
        order_date: e.orderDate,
        bottle_count: e.bottleCount,
      })),
    },
  });
  return {
    saved: wire.saved,
    failed: wire.failed,
    results: wire.results.map((r) => ({
      orderDate: r.order_date,
      ok: r.ok,
      error: r.error,
    })),
  };
}

export async function correctEntry(
  storeId: string,
  orderDate: string,
  bottleCount: number | null,
): Promise<OrderCalendar> {
  return toCalendar(
    await apiRequest("/orders/entry", {
      method: "PATCH",
      body: { store_id: storeId, order_date: orderDate, bottle_count: bottleCount },
    }),
  );
}

/** An employee corrects (or clears, with no count) an entry they marked themselves. */
export async function correctOwnEntry(
  storeId: string,
  orderDate: string,
  bottleCount: number | null,
): Promise<OrderCalendar> {
  return toCalendar(
    await apiRequest("/orders/my-entry", {
      method: "PATCH",
      body: { store_id: storeId, order_date: orderDate, bottle_count: bottleCount },
    }),
  );
}

/** The dashboard numbers for ONE platform (Blinkit and Zepto are never added together). */
export async function getInsights(partner?: string): Promise<DashboardInsights> {
  const qs = partner ? `?partner=${encodeURIComponent(partner)}` : "";
  return toInsights(await apiRequest(`/orders/insights${qs}`));
}

export async function getDailyOverview(partner: string, dayOffset: number): Promise<DailyOverview> {
  const qs = new URLSearchParams({ partner, day_offset: String(dayOffset) });
  return toOverview(await apiRequest(`/orders/daily-overview?${qs}`));
}

export async function importOrdersFile(platform: string, file: File, overwrite: boolean): Promise<OrderImportResult> {
  const body = new FormData();
  body.append("platform", platform);
  body.append("overwrite", String(overwrite));
  body.append("file", file);
  const wire = await apiRequest<Parameters<typeof toOrderImportResult>[0]>("/orders/import", { method: "POST", body });
  return toOrderImportResult(wire);
}

/** Pull order counts from the configured Google Sheet(s). Omit `platform` to sync every sheet. */
export async function syncOrders(platform?: string, overwrite?: boolean): Promise<OrderImportResult[]> {
  const qs = new URLSearchParams();
  if (platform) qs.set("platform", platform);
  if (overwrite !== undefined) qs.set("overwrite", String(overwrite));
  const wire = await apiRequest<Parameters<typeof toOrderImportResult>[0][]>(`/orders/sync${qs.size ? `?${qs}` : ""}`, { method: "POST" });
  return wire.map(toOrderImportResult);
}
