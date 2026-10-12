/**
 * API client for the vendor / POC app (/api/v1/external/*). It is separate from services/api.ts on purpose:
 * vendors have their own sessions, so their token and "signed in" hint never mix with a staff sign-in.
 * Shapes are kept exactly as the API sends them (snake_case).
 */
const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "/api/v1";
const HINT_KEY = "veekay.vendor.session";
const COOKIE_MODE = { "X-Auth-Mode": "cookie" } as const;

let accessToken: string | null = null;
let onExpired: (() => void) | null = null;

export class VendorApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

export function setVendorToken(token: string | null) {
  accessToken = token;
  try {
    if (token) localStorage.setItem(HINT_KEY, "1");
    else localStorage.removeItem(HINT_KEY);
  } catch {
    /* private mode: the session just won't survive a reload */
  }
}

export function hasVendorHint(): boolean {
  try {
    return localStorage.getItem(HINT_KEY) === "1";
  } catch {
    return false;
  }
}

export function setOnVendorExpired(fn: () => void) {
  onExpired = fn;
}

async function refresh(): Promise<boolean> {
  try {
    const res = await fetch(`${BASE_URL}/external/auth/refresh`, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json", ...COOKIE_MODE },
      body: "{}",
    });
    if (!res.ok) return false;
    setVendorToken((await res.json()).access_token);
    return true;
  } catch {
    return false;
  }
}

let inFlight: Promise<boolean> | null = null;

/** One refresh at a time; a second try shortly after covers another tab having just rotated the cookie. */
export function refreshVendorToken(): Promise<boolean> {
  if (!inFlight) {
    inFlight = (async () => {
      if (await refresh()) return true;
      await new Promise((r) => setTimeout(r, 400));
      return refresh();
    })().finally(() => {
      inFlight = null;
    });
  }
  return inFlight;
}

function messageOf(detail: unknown): string {
  if (typeof detail === "string" && detail) return detail;
  if (Array.isArray(detail)) {
    const parts = detail
      .map((d) => (d && typeof d === "object" && "msg" in d ? String((d as { msg: unknown }).msg) : ""))
      .filter(Boolean);
    if (parts.length) return parts.join("; ");
  }
  return "Something went wrong. Please try again.";
}

interface Options {
  method?: "GET" | "POST" | "DELETE";
  body?: unknown;
  retried?: boolean;
  noRefresh?: boolean;
}

async function send(path: string, o: Options): Promise<Response> {
  const isForm = o.body instanceof FormData;
  const headers: Record<string, string> = { ...COOKIE_MODE };
  if (o.body !== undefined && !isForm) headers["Content-Type"] = "application/json";
  if (accessToken) headers.Authorization = `Bearer ${accessToken}`;
  let res: Response;
  try {
    res = await fetch(`${BASE_URL}${path}`, {
      method: o.method ?? "GET",
      credentials: "include",
      headers,
      body: o.body === undefined ? undefined : isForm ? (o.body as FormData) : JSON.stringify(o.body),
    });
  } catch {
    throw new VendorApiError(0, "No connection. Check your internet and try again.");
  }
  if (res.status === 401 && !o.retried && !o.noRefresh) {
    if (await refreshVendorToken()) return send(path, { ...o, retried: true });
    setVendorToken(null);
    onExpired?.();
    throw new VendorApiError(401, "Your session has expired. Please sign in again.");
  }
  return res;
}

export async function vendorRequest<T>(path: string, o: Options = {}): Promise<T> {
  const res = await send(path, o);
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new VendorApiError(res.status, messageOf(body.detail));
  }
  return res.status === 204 ? (undefined as T) : ((await res.json()) as T);
}

export async function vendorBlob(path: string): Promise<Blob> {
  const res = await send(path, {});
  if (!res.ok) throw new VendorApiError(res.status, "Couldn't open that file.");
  return res.blob();
}

/** Opens an authenticated file (photo / PDF) in a new tab. */
export async function openVendorFile(path: string): Promise<void> {
  const win = window.open("", "_blank");
  try {
    const url = URL.createObjectURL(await vendorBlob(path));
    if (win) win.location.href = url;
    else window.location.href = url;
    setTimeout(() => URL.revokeObjectURL(url), 60_000);
  } catch (e) {
    win?.close();
    throw e;
  }
}

function qs(params: Record<string, string | number | undefined | null>): string {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== null && v !== "") p.set(k, String(v));
  const s = p.toString();
  return s ? `?${s}` : "";
}

// ------------------------------------------------------------------ types

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
export interface Notification { id: string; kind: string; title: string; body: string; ref_id: string | null; read: boolean; created_at: string }
export interface NotificationPage extends Paged { items: Notification[]; unread: number }

// ------------------------------------------------------------------ calls

export const vendorApi = {
  async login(email: string, password: string): Promise<void> {
    const res = await vendorRequest<{ access_token: string }>("/external/auth/login", {
      method: "POST", body: { email, password }, noRefresh: true,
    });
    setVendorToken(res.access_token);
  },
  async logout(): Promise<void> {
    await vendorRequest("/external/auth/logout", { method: "POST", body: {}, noRefresh: true }).catch(() => undefined);
    setVendorToken(null);
  },
  me: () => vendorRequest<Me>("/external/me"),
  stores: () => vendorRequest<StoreRef[]>("/external/stores"),
  orders: (p: { store_id?: string; date_from?: string; date_to?: string; page?: number; page_size?: number }) =>
    vendorRequest<OrderPage>(`/external/orders${qs(p)}`),
  dailyOrders: (p: { store_id?: string; date_from?: string; date_to?: string }) => vendorRequest<DayTotal[]>(`/external/orders/daily${qs(p)}`),
  tickets: (p: { store_id?: string; status?: string; page?: number; page_size?: number }) =>
    vendorRequest<TicketPage>(`/external/tickets${qs(p)}`),
  ticket: (id: string) => vendorRequest<TicketDetail>(`/external/tickets/${id}`),
  raiseTicket: (form: FormData) => vendorRequest<TicketDetail>("/external/tickets", { method: "POST", body: form }),
  reply: (id: string, form: FormData) => vendorRequest<TicketDetail>(`/external/tickets/${id}/comments`, { method: "POST", body: form }),
  documents: (p: { store_id?: string; kind?: string; month?: string; page?: number; page_size?: number }) =>
    vendorRequest<DocumentPage>(`/external/documents${qs(p)}`),
  uploadDocument: (form: FormData) => vendorRequest<DocumentRow>("/external/documents", { method: "POST", body: form }),
  bottles: (p: { store_id?: string; page?: number; page_size?: number }) => vendorRequest<BottlePage>(`/external/bottles${qs(p)}`),
  deliveries: (p: { store_id?: string; page?: number; page_size?: number }) => vendorRequest<DeliveryPage>(`/external/deliveries${qs(p)}`),
  confirmDelivery: (form: FormData) => vendorRequest<Delivery>("/external/deliveries", { method: "POST", body: form }),
  notifications: (p: { page?: number; page_size?: number } = {}) => vendorRequest<NotificationPage>(`/external/notifications${qs(p)}`),
  markRead: (ids?: string[]) => vendorRequest<void>("/external/notifications/read", { method: "POST", body: ids ? { ids } : {} }),
};
