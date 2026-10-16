/**
 * HTTP client for the Veekay API (/external/*). The access token lives in memory only; the refresh token is kept in
 * the Android Keystore (expo-secure-store) and rotates on every refresh. A 401 triggers one silent refresh and a retry.
 */
import { fetch as expoFetch } from "expo/fetch";
import * as SecureStore from "expo-secure-store";
import { connectivity, MESSAGES, type FailureKind } from "@/lib/connectivityCore";

const DEV_DEFAULT = "http://10.0.2.2:8000/api/v1"; // Android emulator -> your computer
const RAW_URL = (process.env.EXPO_PUBLIC_API_URL ?? (__DEV__ ? DEV_DEFAULT : "")).replace(/\/+$/, "");

// Only a LAN test build (APP_VARIANT=development, checked again in app.config.ts) may talk plain http, to a computer on the same Wi-Fi.
const ALLOW_HTTP = process.env.EXPO_PUBLIC_ALLOW_HTTP === "1";

/** A release build must talk https; anything else is a packaging mistake we surface instead of shipping silently. */
export const configError: string | null = !RAW_URL
  ? "The app is not configured: the server address is missing."
  : !__DEV__ && !ALLOW_HTTP && !RAW_URL.startsWith("https://")
    ? "The app is not configured: the server address must use https."
    : null;

const BASE = RAW_URL;
export const apiBaseUrl = BASE;
const REFRESH_KEY = "veekay.refresh";
const KIND_KEY = "veekay.kind";

/** Vendors and POCs sign in against /external/auth, Veekay employees against /auth. Each has its own refresh route. */
export type SessionKind = "partner" | "staff";
const AUTH_PATH: Record<SessionKind, string> = { partner: "/external/auth", staff: "/auth" };
const TIMEOUT_MS = 30_000;
const UPLOAD_TIMEOUT_MS = 90_000;

let accessToken: string | null = null;
let onExpired: (() => void) | null = null;

export class ApiError extends Error {
  status: number;
  /** Set when the request never got an answer (status 0): why, so screens and the banner can word it correctly. */
  kind?: FailureKind;
  constructor(status: number, message: string, kind?: FailureKind) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.kind = kind;
  }
}

export function setOnSessionExpired(fn: () => void) {
  onExpired = fn;
}

export async function storedSessionKind(): Promise<SessionKind | null> {
  const [token, kind] = await Promise.all([SecureStore.getItemAsync(REFRESH_KEY), SecureStore.getItemAsync(KIND_KEY)]);
  return token && (kind === "partner" || kind === "staff") ? kind : null;
}

/** Keeps the tokens of a new or rotated session. `kind` is only given at sign-in. */
export async function adoptTokens(pair: { access_token: string; refresh_token?: string | null }, kind?: SessionKind) {
  accessToken = pair.access_token;
  if (pair.refresh_token) await SecureStore.setItemAsync(REFRESH_KEY, pair.refresh_token);
  if (kind) await SecureStore.setItemAsync(KIND_KEY, kind);
}

export async function clearSession() {
  accessToken = null;
  await SecureStore.deleteItemAsync(REFRESH_KEY).catch(() => undefined);
  await SecureStore.deleteItemAsync(KIND_KEY).catch(() => undefined);
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

async function timedFetch(url: string, init: RequestInit, ms: number): Promise<Response> {
  const ctl = new AbortController();
  const timer = setTimeout(() => ctl.abort(), ms);
  try {
    const res = (await expoFetch(url, { ...(init as object), signal: ctl.signal } as never)) as unknown as Response;
    connectivity.reportSuccess(); // any answer, even an error status, proves the phone and the server can talk
    return res;
  } catch (e) {
    // Only the phone's own network state may say "no internet". With a network, a failure means the server was
    // not reachable (or too slow), which is a different message and a different banner.
    const timedOut = e instanceof Error && e.name === "AbortError";
    const kind: FailureKind = connectivity.isDeviceOffline() ? "offline" : timedOut ? "timeout" : "unreachable";
    connectivity.reportFailure(kind);
    throw new ApiError(0, MESSAGES[kind], kind);
  } finally {
    clearTimeout(timer);
  }
}

let refreshing: Promise<boolean> | null = null;

/** One refresh at a time. A server error or no network keeps the stored session; only a real refusal ends it. */
export function refreshSession(): Promise<boolean> {
  if (!refreshing) {
    refreshing = (async () => {
      const token = await SecureStore.getItemAsync(REFRESH_KEY);
      const kind = await storedSessionKind();
      if (!token || !kind) return false;
      try {
        const res = await timedFetch(`${BASE}${AUTH_PATH[kind]}/refresh`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ refresh_token: token }),
        }, TIMEOUT_MS);
        if (res.ok) {
          await adoptTokens(await res.json());
          return true;
        }
        if (res.status === 401) await clearSession();
        return false;
      } catch {
        return false;
      }
    })().finally(() => {
      refreshing = null;
    });
  }
  return refreshing;
}

interface Options {
  method?: "GET" | "POST" | "DELETE";
  body?: unknown;
  retried?: boolean;
  noRefresh?: boolean;
  /** Same key on every retry of one submission: the server then returns the first result instead of creating a duplicate. */
  idempotencyKey?: string;
}

async function send(path: string, o: Options): Promise<Response> {
  if (configError) throw new ApiError(0, configError);
  const isForm = typeof FormData !== "undefined" && o.body instanceof FormData;
  const headers: Record<string, string> = { Accept: "application/json" };
  if (o.body !== undefined && !isForm) headers["Content-Type"] = "application/json";
  if (accessToken) headers.Authorization = `Bearer ${accessToken}`;
  if (o.idempotencyKey) headers["Idempotency-Key"] = o.idempotencyKey;
  const res = await timedFetch(
    `${BASE}${path}`,
    { method: o.method ?? "GET", headers, body: o.body === undefined ? undefined : isForm ? (o.body as FormData) : JSON.stringify(o.body) },
    isForm ? UPLOAD_TIMEOUT_MS : TIMEOUT_MS,
  );
  if (res.status === 401 && !o.retried && !o.noRefresh) {
    if (await refreshSession()) return send(path, { ...o, retried: true });
    accessToken = null;
    onExpired?.();
    throw new ApiError(401, "Your session has expired. Please sign in again.");
  }
  return res;
}

export async function request<T>(path: string, o: Options = {}): Promise<T> {
  const res = await send(path, o);
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new ApiError(res.status, messageOf((body as { detail?: unknown }).detail));
  }
  return res.status === 204 ? (undefined as T) : ((await res.json()) as T);
}

/** Raw bytes of an authenticated file (a ticket photo or a document). */
export async function requestBytes(path: string): Promise<{ bytes: Uint8Array; contentType: string }> {
  const res = await send(path, {});
  if (!res.ok) throw new ApiError(res.status, "Couldn't open that file.");
  return { bytes: await res.bytes(), contentType: res.headers.get("content-type") ?? "application/octet-stream" };
}

export async function signInPartner(email: string, password: string): Promise<void> {
  const res = await request<{ access_token: string; refresh_token: string }>("/external/auth/login", {
    method: "POST",
    body: { email: email.trim().toLowerCase(), password },
    noRefresh: true,
  });
  await adoptTokens(res, "partner");
}

export async function signInStaff(employeeCode: string, password: string): Promise<void> {
  const res = await request<{ access_token: string; refresh_token: string }>("/auth/login", {
    method: "POST",
    body: { employee_code: employeeCode.trim().toUpperCase(), password },
    noRefresh: true,
  });
  await adoptTokens(res, "staff");
}

export async function signOut(): Promise<void> {
  const [token, kind] = await Promise.all([SecureStore.getItemAsync(REFRESH_KEY), storedSessionKind()]);
  if (token && kind) {
    await request(`${AUTH_PATH[kind]}/logout`, { method: "POST", body: { refresh_token: token }, noRefresh: true }).catch(() => undefined);
  }
  await clearSession();
}
