/**
 * Single fetch wrapper for every API call. Never call fetch() directly
 * from a feature — this is the only place that knows about base URL,
 * auth headers, refresh-on-401, and error surfacing, so that behavior
 * is consistent everywhere (spec section 2: frontend only talks to
 * the Veekay API).
 */
import { pushToast } from "@/lib/toast";

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "/api/v1";
// The refresh token never reaches JavaScript: the API keeps it in an HttpOnly cookie (we ask for that with
// the X-Auth-Mode header). Only a non-secret "signed in" hint is stored so a page reload knows to try restoring.
const SESSION_HINT_KEY = "veekay.session";
const AUTH_MODE = { "X-Auth-Mode": "cookie" } as const;

let accessToken: string | null = null;
let onSessionExpired: (() => void) | null = null;

export function setAccessToken(token: string | null) {
  accessToken = token;
  try {
    if (token !== null) localStorage.setItem(SESSION_HINT_KEY, "1");
    else localStorage.removeItem(SESSION_HINT_KEY);
  } catch {
    /* storage unavailable (private mode): session just won't survive a reload */
  }
}

export function hasSessionHint(): boolean {
  try {
    return localStorage.getItem(SESSION_HINT_KEY) === "1";
  } catch {
    return false;
  }
}

export function setOnSessionExpired(handler: () => void) {
  onSessionExpired = handler;
}

let onPasswordChangeRequired: (() => void) | null = null;

/** Called when the server says a temporary password must be replaced before anything else. */
export function setOnPasswordChangeRequired(handler: () => void) {
  onPasswordChangeRequired = handler;
}

const PASSWORD_GATE = "PASSWORD_CHANGE_REQUIRED";

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function doRefresh(): Promise<boolean> {
  try {
    const res = await fetch(`${BASE_URL}/auth/refresh`, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json", ...AUTH_MODE },
      body: "{}",
    });
    if (!res.ok) return false;
    const data = await res.json();
    setAccessToken(data.access_token);
    return true;
  } catch {
    return false;
  }
}

let refreshInFlight: Promise<boolean> | null = null;

/** One refresh at a time: parallel 401s share it. If another tab rotated the cookie a moment ago, retry once. */
export function refreshAccessToken(): Promise<boolean> {
  if (!refreshInFlight) {
    refreshInFlight = (async () => {
      if (await doRefresh()) return true;
      await new Promise((r) => setTimeout(r, 400));
      return doRefresh();
    })().finally(() => {
      refreshInFlight = null;
    });
  }
  return refreshInFlight;
}

interface RequestOptions {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  body?: unknown;
  isRetry?: boolean;
  /** Suppress the automatic error toast — for calls where the caller
   * wants to show its own inline error instead (e.g. the login form). */
  silent?: boolean;
  /** Skip the refresh-on-401 / "session expired" handling. Set for the
   * login request itself: a 401 there means bad credentials, not an
   * expired session, and there's no session to refresh yet. */
  skipAuthRefresh?: boolean;
}

/** FastAPI sends `detail` as a string, or (for validation errors) a list of {loc, msg} — always turn it into text. */
function errorMessage(detail: unknown): string {
  if (typeof detail === "string" && detail) return detail;
  if (Array.isArray(detail)) {
    const parts = detail
      .map((d) => {
        const msg = typeof d === "object" && d && "msg" in d ? String((d as { msg: unknown }).msg) : "";
        const loc = typeof d === "object" && d && "loc" in d && Array.isArray((d as { loc: unknown[] }).loc) ? String((d as { loc: unknown[] }).loc.at(-1) ?? "") : "";
        return msg ? (loc && loc !== "body" ? `${loc}: ${msg}` : msg) : "";
      })
      .filter(Boolean);
    if (parts.length) return parts.join("; ");
  }
  return "Something went wrong. Please try again.";
}

export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const isForm = options.body instanceof FormData;
  const headers: Record<string, string> = { ...AUTH_MODE };
  // Let the browser set the multipart boundary itself for FormData.
  if (!isForm) headers["Content-Type"] = "application/json";
  if (accessToken) headers.Authorization = `Bearer ${accessToken}`;

  let res: Response;
  try {
    res = await fetch(`${BASE_URL}${path}`, {
      method: options.method ?? "GET",
      credentials: "include",
      headers,
      body: isForm
        ? (options.body as FormData)
        : options.body
          ? JSON.stringify(options.body)
          : undefined,
    });
  } catch {
    const message = "Unable to connect. Please check your connection and try again.";
    if (!options.silent) pushToast(message, "error");
    throw new ApiError(0, message);
  }

  if (res.status === 401 && !options.isRetry && !options.skipAuthRefresh) {
    const refreshed = await refreshAccessToken();
    if (refreshed) {
      return apiRequest<T>(path, { ...options, isRetry: true });
    }
    setAccessToken(null);
    onSessionExpired?.();
    const message = "Your session has expired. Please sign in again.";
    if (!options.silent) pushToast(message, "error");
    throw new ApiError(401, message);
  }

  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    if (res.status === 403 && body.detail === PASSWORD_GATE) {
      onPasswordChangeRequired?.();
      throw new ApiError(403, "Please choose a new password to continue.");
    }
    const message = errorMessage(body.detail);
    if (!options.silent) pushToast(message, "error");
    throw new ApiError(res.status, message);
  }

  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

/** Authenticated binary download/view (e.g. a stored document). Refreshes the token once on 401. */
export async function apiBlob(
  path: string,
  options: { method?: "GET" | "POST"; body?: unknown; isRetry?: boolean } = {},
): Promise<Blob> {
  const headers: Record<string, string> = { ...AUTH_MODE };
  if (options.body) headers["Content-Type"] = "application/json";
  if (accessToken) headers.Authorization = `Bearer ${accessToken}`;

  let res: Response;
  try {
    res = await fetch(`${BASE_URL}${path}`, {
      method: options.method ?? "GET",
      credentials: "include",
      headers,
      body: options.body ? JSON.stringify(options.body) : undefined,
    });
  } catch {
    const message = "Unable to connect. Please check your connection and try again.";
    pushToast(message, "error");
    throw new ApiError(0, message);
  }

  if (res.status === 401 && !options.isRetry) {
    if (await refreshAccessToken()) return apiBlob(path, { ...options, isRetry: true });
    setAccessToken(null);
    onSessionExpired?.();
    throw new ApiError(401, "Your session has expired. Please sign in again.");
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    if (res.status === 403 && body.detail === PASSWORD_GATE) {
      onPasswordChangeRequired?.();
      throw new ApiError(403, "Please choose a new password to continue.");
    }
    const message: string = body.detail ?? "Couldn't load that file.";
    pushToast(message, "error");
    throw new ApiError(res.status, message);
  }
  return res.blob();
}
