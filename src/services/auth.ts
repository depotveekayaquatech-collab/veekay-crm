import { apiRequest, setTokens } from "@/services/api";
import type { CurrentUser } from "@/types/auth";

interface LoginPayload {
  organizationSlug: string;
  employeeCode: string;
  password: string;
}

interface TokenResponse {
  access_token: string;
  refresh_token: string;
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
  };
}

export async function login(payload: LoginPayload): Promise<CurrentUser> {
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
  return toCurrentUser(await apiRequest<MeResponse>("/auth/me"));
}

export async function logout(): Promise<void> {
  await apiRequest("/auth/logout", { method: "POST", silent: true }).catch(() => undefined);
  setTokens(null);
}

export async function fetchCurrentUser(silent = false): Promise<CurrentUser> {
  return toCurrentUser(await apiRequest<MeResponse>("/auth/me", { silent }));
}
