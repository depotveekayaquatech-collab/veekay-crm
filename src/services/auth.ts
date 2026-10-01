import { apiRequest, getCurrentRefreshToken, setTokens } from "@/services/api";
import type { CurrentUser } from "@/types/auth";

interface LoginPayload {
  organizationSlug: string;
  employeeCode: string;
  password: string;
}

interface TokenResponse {
  access_token: string;
  refresh_token: string;
  /** true when this sign-in counts as attendance (employees / accounts — never admins) */
  attendance?: boolean;
}

interface MeResponse {
  id: string;
  employee_code: string;
  full_name: string;
  email: string | null;
  organization_id: string;
  organization_slug: string;
  platform_slug: string | null;
  platform_label: string | null;
  region_id: string | null;
  region_name: string | null;
  permissions: string[];
  roles: string[];
  is_admin: boolean;
  must_change_password?: boolean;
}

function toCurrentUser(res: MeResponse): CurrentUser {
  return {
    id: res.id,
    employeeCode: res.employee_code,
    fullName: res.full_name,
    email: res.email,
    organizationId: res.organization_id,
    organizationSlug: res.organization_slug,
    platformSlug: res.platform_slug,
    platformLabel: res.platform_label,
    regionId: res.region_id,
    regionName: res.region_name,
    permissions: res.permissions,
    roles: res.roles,
    isAdmin: res.is_admin,
    mustChangePassword: res.must_change_password ?? false,
  };
}

/**
 * Sign in. `afterSignIn` runs right after a successful login, but only when the server says this sign-in
 * counts as attendance — that is the one moment the device location is read. Admins never trigger it.
 */
export async function login(payload: LoginPayload, afterSignIn?: () => Promise<void>): Promise<CurrentUser> {
  const tokens = await apiRequest<TokenResponse>("/auth/login", {
    method: "POST",
    silent: true,
    skipAuthRefresh: true,
    body: {
      organization_slug: payload.organizationSlug,
      employee_code: payload.employeeCode,
      password: payload.password,
    },
  });
  setTokens({ accessToken: tokens.access_token, refreshToken: tokens.refresh_token });
  if (tokens.attendance && afterSignIn) {
    try {
      await afterSignIn();
    } catch {
      /* a missing location never blocks signing in */
    }
  }
  return toCurrentUser(await apiRequest<MeResponse>("/auth/me"));
}

export async function logout(): Promise<void> {
  // Revoke the session server-side (best effort), then forget the tokens locally.
  const rt = getCurrentRefreshToken();
  await apiRequest("/auth/logout", { method: "POST", body: { refresh_token: rt }, silent: true, skipAuthRefresh: true }).catch(() => undefined);
  setTokens(null);
}

/** Change your own password. Every device is signed out; this one gets a fresh session. */
export async function changePassword(currentPassword: string, newPassword: string): Promise<CurrentUser> {
  const tokens = await apiRequest<TokenResponse>("/auth/change-password", {
    method: "POST",
    body: { current_password: currentPassword, new_password: newPassword },
    silent: true,
  });
  setTokens({ accessToken: tokens.access_token, refreshToken: tokens.refresh_token });
  return toCurrentUser(await apiRequest<MeResponse>("/auth/me"));
}

export interface SessionInfo {
  id: string;
  current: boolean;
  signedInAt: string;
  lastActiveAt: string;
  ip: string | null;
  userAgent: string | null;
}

export async function listSessions(): Promise<SessionInfo[]> {
  const rows = await apiRequest<
    { id: string; current: boolean; signed_in_at: string; last_active_at: string; ip: string | null; user_agent: string | null }[]
  >("/auth/sessions");
  return rows.map((r) => ({
    id: r.id, current: r.current, signedInAt: r.signed_in_at, lastActiveAt: r.last_active_at, ip: r.ip, userAgent: r.user_agent,
  }));
}

export async function revokeSession(id: string): Promise<void> {
  await apiRequest(`/auth/sessions/${id}`, { method: "DELETE" });
}

export async function fetchCurrentUser(silent = false): Promise<CurrentUser> {
  return toCurrentUser(await apiRequest<MeResponse>("/auth/me", { silent }));
}

/** Attach the device location to the sign-in that just happened (allowed once, right after login). */
export async function recordLoginLocation(loc: { latitude: number; longitude: number; accuracy: number }): Promise<void> {
  await apiRequest("/attendance/location", { method: "POST", body: loc, silent: true }).catch(() => undefined);
}
