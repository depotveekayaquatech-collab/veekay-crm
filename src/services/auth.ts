import { apiRequest, setTokens } from "@/services/api";
import type { CurrentUser } from "@/types/auth";

interface LoginPayload {
  organizationSlug: string;
  email: string;
  password: string;
}

interface TokenResponse {
  access_token: string;
  refresh_token: string;
}

interface MeResponse {
  id: string;
  full_name: string;
  email: string;
  organization_id: string;
  organization_slug: string;
  permissions: string[];
  roles: string[];
}

function toCurrentUser(res: MeResponse): CurrentUser {
  return {
    id: res.id,
    fullName: res.full_name,
    email: res.email,
    organizationId: res.organization_id,
    organizationSlug: res.organization_slug,
    permissions: res.permissions,
    roles: res.roles,
  };
}

export async function login(payload: LoginPayload): Promise<CurrentUser> {
  // silent: true — LoginPage shows its own inline error instead of a
  // toast, since the form field is right there for it.
  const tokens = await apiRequest<TokenResponse>("/auth/login", {
    method: "POST",
    silent: true,
    skipAuthRefresh: true,
    body: {
      organization_slug: payload.organizationSlug,
      email: payload.email,
      password: payload.password,
    },
  });
  setTokens({ accessToken: tokens.access_token, refreshToken: tokens.refresh_token });
  const me = await apiRequest<MeResponse>("/auth/me");
  return toCurrentUser(me);
}

export async function logout(): Promise<void> {
  await apiRequest("/auth/logout", { method: "POST", silent: true }).catch(() => undefined);
  setTokens(null);
}

export async function fetchCurrentUser(silent = false): Promise<CurrentUser> {
  const me = await apiRequest<MeResponse>("/auth/me", { silent });
  return toCurrentUser(me);
}
