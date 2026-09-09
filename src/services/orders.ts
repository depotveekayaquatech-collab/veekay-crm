import { apiRequest } from "@/services/api";
import {
  toCalendar,
  toInsights,
  toMyStore,
  toOverview,
  type DashboardInsights,
  type DailyOverview,
  type MyStore,
  type OrderCalendar,
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

export async function getInsights(): Promise<DashboardInsights> {
  return toInsights(await apiRequest("/orders/insights"));
}

export async function getDailyOverview(partner: string, dayOffset: number): Promise<DailyOverview> {
  const qs = new URLSearchParams({ partner, day_offset: String(dayOffset) });
  return toOverview(await apiRequest(`/orders/daily-overview?${qs}`));
}
