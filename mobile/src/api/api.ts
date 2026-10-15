import { request, signInPartner, signOut } from "@/api/client";

function qs(params: Record<string, string | number | undefined | null>): string {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== null && v !== "") p.set(k, String(v));
  const s = p.toString();
  return s ? `?${s}` : "";
}

export interface Me { id: string; kind: "vendor" | "poc"; email: string; full_name: string; phone: string | null; platforms: string[]; store_count: number }
export interface StoreRef { id: string; name: string; code: string; platform: string | null; city: string | null; state: string | null }
export interface Paged { total: number; page: number; page_size: number }
export interface OrderRow { store_id: string; store_name: string; order_date: string; bottle_count: number }
export interface DayTotal { order_date: string; bottles: number; stores: number }
export interface OrderPage extends Paged { items: OrderRow[]; total_bottles: number }
export type TicketStatus = "OPEN" | "IN_PROGRESS" | "RESOLVED" | "CLOSED";
export interface TicketRow {
  id: string; number: number; store_id: string; store_name: string; category: string; priority: string; status: TicketStatus;
  title: string; created_at: string; due_at: string | null; resolved_at: string | null;
}
export interface TicketPage extends Paged { items: TicketRow[] }
export interface TicketComment { id: string; body: string; event: string | null; mine: boolean; created_at: string }
export interface Attachment { id: string; comment_id: string | null; file_name: string; content_type: string; size_bytes: number }
export interface TicketDetail extends TicketRow { description: string | null; comments: TicketComment[]; attachments: Attachment[] }
export interface DocumentRow {
  id: string; store_id: string; store_name: string; month: string; kind: "card" | "bill" | "payment"; file_name: string;
  content_type: string; size_bytes: number; updated_at: string; due_date: string | null; status: "PENDING" | "CLEARED" | null;
}
export interface DocumentPage extends Paged { items: DocumentRow[] }
export interface BottleRow { serial: string; store_id: string; store_name: string; last_in_at: string | null }
export interface BottlePage extends Paged { items: BottleRow[]; per_store: Record<string, number> }
export type Outcome = "RECEIVED" | "SHORT" | "DAMAGED";
export interface Delivery {
  id: string; store_id: string; store_name: string; delivery_date: string; outcome: Outcome; expected_qty: number | null;
  received_qty: number | null; note: string | null; ticket_id: string | null; reported_by: string; created_at: string;
}
export interface DeliveryPage extends Paged { items: Delivery[] }
export interface AppNotification { id: string; kind: string; title: string; body: string; ref_id: string | null; read: boolean; created_at: string }
export interface NotificationPage extends Paged { items: AppNotification[]; unread: number }

export const api = {
  signIn: signInPartner,
  signOut,
  me: () => request<Me>("/external/me"),
  stores: () => request<StoreRef[]>("/external/stores"),
  orders: (p: { store_id?: string; date_from?: string; date_to?: string; page?: number; page_size?: number }) =>
    request<OrderPage>(`/external/orders${qs(p)}`),
  dailyOrders: (p: { store_id?: string; date_from?: string; date_to?: string }) => request<DayTotal[]>(`/external/orders/daily${qs(p)}`),
  tickets: (p: { store_id?: string; status?: string; page?: number; page_size?: number }) => request<TicketPage>(`/external/tickets${qs(p)}`),
  ticket: (id: string) => request<TicketDetail>(`/external/tickets/${id}`),
  raiseTicket: (form: FormData, key?: string) => request<TicketDetail>("/external/tickets", { method: "POST", body: form, idempotencyKey: key }),
  reply: (id: string, form: FormData, key?: string) => request<TicketDetail>(`/external/tickets/${id}/comments`, { method: "POST", body: form, idempotencyKey: key }),
  documents: (p: { store_id?: string; kind?: string; month?: string; page?: number; page_size?: number }) =>
    request<DocumentPage>(`/external/documents${qs(p)}`),
  uploadDocument: (form: FormData, key?: string) => request<DocumentRow>("/external/documents", { method: "POST", body: form, idempotencyKey: key }),
  bottles: (p: { store_id?: string; page?: number; page_size?: number }) => request<BottlePage>(`/external/bottles${qs(p)}`),
  deliveries: (p: { store_id?: string; page?: number; page_size?: number }) => request<DeliveryPage>(`/external/deliveries${qs(p)}`),
  confirmDelivery: (form: FormData) => request<Delivery>("/external/deliveries", { method: "POST", body: form }),
  notifications: (p: { page?: number; page_size?: number } = {}) => request<NotificationPage>(`/external/notifications${qs(p)}`),
  markRead: (ids?: string[]) => request<void>("/external/notifications/read", { method: "POST", body: ids ? { ids } : {} }),
  registerDevice: (token: string) => request<void>("/external/devices", { method: "POST", body: { token, platform: "android" } }),
  unregisterDevice: (token: string) => request<void>(`/external/devices${qs({ token })}`, { method: "DELETE" }),
};
