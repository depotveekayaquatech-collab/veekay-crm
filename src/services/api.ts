/**
 * Single fetch wrapper for every API call. Never call fetch() directly
 * from a feature — this is the only place that knows about base URL,
 * auth headers, refresh-on-401, and error surfacing, so that behavior
 * is consistent everywhere (spec section 2: frontend only talks to
 * the Veekay API).
 */
import { pushToast } from "@/lib/toast";

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "/api/v1";
const REFRESH_TOKEN_STORAGE_KEY = "veekay.refreshToken";

let accessToken: string | null = null;
let refreshToken: string | null = null;
let onSessionExpired: (() => void) | null = null;

export function setTokens(tokens: { accessToken: string; refreshToken: string } | null) {
  accessToken = tokens?.accessToken ?? null;
  refreshToken = tokens?.refreshToken ?? null;
  // Only the refresh token is persisted, and only in localStorage for this
  // scaffold. That's a deliberate trade-off, not an oversight — an httpOnly
  // cookie is the safer place for it against XSS, but that requires the
  // backend to set cookies instead of returning tokens in the JSON body.
  // Revisit this before production (spec section 46's security review).
  if (tokens?.refreshToken) {
    localStorage.setItem(REFRESH_TOKEN_STORAGE_KEY, tokens.refreshToken);
  } else {
    localStorage.removeItem(REFRESH_TOKEN_STORAGE_KEY);
  }
}

export function getPersistedRefreshToken(): string | null {
  return localStorage.getItem(REFRESH_TOKEN_STORAGE_KEY);
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

async function doRefresh(tokenToUse: string): Promise<boolean> {
  try {
    const res = await fetch(`${BASE_URL}/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: tokenToUse }),
    });
    if (!res.ok) return false;
    const data = await res.json();
    setTokens({ accessToken: data.access_token, refreshToken: data.refresh_token });
    return true;
  } catch {
    return false;
  }
}

let refreshInFlight: Promise<boolean> | null = null;

/** One refresh at a time: parallel 401s share it, so a rotated refresh token is never presented twice. */
function refreshAccessToken(): Promise<boolean> {
  if (!refreshInFlight) {
    refreshInFlight = (async () => {
      const used = refreshToken ?? getPersistedRefreshToken();
      if (!used) return false;
      if (await doRefresh(used)) return true;
      // Another tab may have rotated the token a moment ago — try whatever is stored now.
      const latest = getPersistedRefreshToken();
      return latest && latest !== used ? doRefresh(latest) : false;
    })().finally(() => {
      refreshInFlight = null;
    });
  }
  return refreshInFlight;
}

/** The refresh token to revoke server-side on sign-out. */
export function getCurrentRefreshToken(): string | null {
  return refreshToken ?? getPersistedRefreshToken();
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

export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const isForm = options.body instanceof FormData;
  const headers: Record<string, string> = {};
  // Let the browser set the multipart boundary itself for FormData.
  if (!isForm) headers["Content-Type"] = "application/json";
  if (accessToken) headers.Authorization = `Bearer ${accessToken}`;

  let res: Response;
  try {
    res = await fetch(`${BASE_URL}${path}`, {
      method: options.method ?? "GET",
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
    setTokens(null);
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
    const message: string = body.detail ?? "Something went wrong. Please try again.";
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
  const headers: Record<string, string> = {};
  if (options.body) headers["Content-Type"] = "application/json";
  if (accessToken) headers.Authorization = `Bearer ${accessToken}`;

  let res: Response;
  try {
    res = await fetch(`${BASE_URL}${path}`, {
      method: options.method ?? "GET",
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
    setTokens(null);
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
