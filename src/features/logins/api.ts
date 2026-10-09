import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { apiBlob, apiRequest } from "@/services/api";
import { camelize } from "@/lib/camel";

export type LoginKind = "vendor" | "poc";

export interface LoginAccount {
  id: string;
  kind: LoginKind;
  email: string;
  fullName: string;
  phone: string | null;
  platforms: string[];
  storeCount: number;
  mustChangePassword: boolean;
  isActive: boolean;
  createdAt: string;
}

export interface LoginList {
  items: LoginAccount[];
  total: number;
  vendors: number;
  pocs: number;
}

export interface LoginStore {
  id: string;
  name: string;
  code: string;
  platform: string | null;
  city: string | null;
  state: string | null;
}

export interface LoginFilters {
  kind: "" | LoginKind;
  platform: string;
  q: string;
}

export const PAGE_SIZE = 50;

function params(f: LoginFilters): URLSearchParams {
  const p = new URLSearchParams();
  if (f.kind) p.set("kind", f.kind);
  if (f.platform) p.set("platform", f.platform);
  if (f.q.trim()) p.set("q", f.q.trim());
  return p;
}

export function useLogins(f: LoginFilters, page: number) {
  return useQuery({
    queryKey: ["logins", f, page],
    queryFn: async () => {
      const p = params(f);
      p.set("page", String(page));
      p.set("page_size", String(PAGE_SIZE));
      return camelize<LoginList>(await apiRequest(`/external-accounts?${p}`));
    },
    placeholderData: keepPreviousData,
  });
}

export function useLoginDetail(id: string | null) {
  return useQuery({
    queryKey: ["login", id],
    enabled: Boolean(id),
    queryFn: async () => camelize<{ account: LoginAccount; stores: LoginStore[] }>(await apiRequest(`/external-accounts/${id}`)),
  });
}

export async function downloadLogins(f: LoginFilters): Promise<void> {
  const blob = await apiBlob(`/external-accounts/export?${params(f)}`);
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "vendor-poc-logins.csv";
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 30_000);
}
