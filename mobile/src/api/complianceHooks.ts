import { keepPreviousData, useQuery, useQueryClient } from "@tanstack/react-query";
import { complianceApi, type ComplianceQuery, type ComplianceRow } from "@/api/complianceApi";
import { DEFAULT_POLICY, type UploadPolicy } from "@/lib/compliance";
import { cacheRemoteFile } from "@/lib/files";

const FRESH = 20_000;

/** The monthly list, one page at a time. The previous page stays on screen while the next one loads. */
export const useComplianceList = (p: ComplianceQuery) =>
  useQuery({ queryKey: ["s-compliance", p], queryFn: () => complianceApi.stores(p), placeholderData: keepPreviousData, staleTime: FRESH });

/** EVERY store of the month in one list (the server pages at 200): what the Inventory needs to count cards and bills per vendor. `month` "" = the server's month. */
export const useAllCompliance = (month: string, enabled = true) =>
  useQuery({
    queryKey: ["s-compliance-all", month],
    enabled,
    staleTime: FRESH,
    placeholderData: keepPreviousData,
    queryFn: async () => {
      const ask = (page: number) => complianceApi.stores({ month: month || undefined, page, page_size: 200 });
      const first = await ask(1);
      const items = [...first.items];
      for (let page = 2; items.length < first.total && page <= 25; page++) items.push(...(await ask(page)).items);
      return { month: first.month, month_label: first.month_label, months: first.months, items };
    },
  });

/** The headline numbers for the month (one tiny request: a page of one store). Used by the dashboard tile. */
export const useComplianceKpis = (enabled: boolean) =>
  useQuery({ queryKey: ["s-compliance-kpis"], queryFn: () => complianceApi.stores({ page_size: 1 }), enabled, staleTime: 60_000 });

/** One store's row, found with the existing list route (searching by its code). Shares the list's cache keys so it refreshes with it. */
export function useComplianceStore(storeId: string, code: string, month?: string) {
  const q = useQuery({
    queryKey: ["s-compliance-store", storeId, month ?? "", code],
    queryFn: async () => {
      const page = await complianceApi.stores({ month, q: code || undefined, page_size: 100 });   // a short code can match many stores: look at plenty
      return { page, row: page.items.find((r) => r.store_id === storeId) ?? null };
    },
    staleTime: FRESH,
    placeholderData: keepPreviousData,
  });
  return { ...q, row: (q.data?.row ?? null) as ComplianceRow | null, months: q.data?.page.months ?? [], month: q.data?.page.month ?? month ?? "" };
}

export const useDocVersions = (id: string | null) =>
  useQuery({ queryKey: ["s-doc-versions", id], queryFn: () => complianceApi.versions(id!), enabled: !!id, staleTime: FRESH });

/** A short-lived link to a stored file (valid 5 minutes; reused for 4 so it is never shown expired). */
export const useDocLink = (id: string | null, version?: number, enabled = true) =>
  useQuery({ queryKey: ["s-doc-link", id, version ?? 0], queryFn: () => complianceApi.link(id!, version), enabled: !!id && enabled, staleTime: 4 * 60_000, gcTime: 5 * 60_000 });

/** The server's upload rules; the defaults are used until it answers (or if it cannot be reached). */
export function useUploadPolicy(): UploadPolicy {
  const q = useQuery({ queryKey: ["s-upload-policy"], queryFn: complianceApi.policy, staleTime: 10 * 60_000, retry: false });
  return q.data ?? DEFAULT_POLICY;
}

/** After any change to a document: the lists, the store page, its history and any link. */
export function useRefreshCompliance() {
  const qc = useQueryClient();
  return () =>
    Promise.all(["s-compliance", "s-compliance-all", "s-compliance-kpis", "s-compliance-store", "s-doc-versions", "s-doc-link", "s-doc-copy"].map((k) => qc.invalidateQueries({ queryKey: [k] })));
}

/**
 * Something that can be shown for a stored file: a short-lived direct link when the server gives one, otherwise a temporary
 * copy fetched through the authenticated route. Nothing is requested until `enabled` (a list never loads a photo per row).
 */
export function useDocFile(id: string | null, version?: number, enabled = true) {
  const link = useDocLink(id, version, enabled);
  const needsCopy = enabled && !!id && !!link.data && !link.data.url;
  const copy = useQuery({
    queryKey: ["s-doc-copy", id, version ?? 0],
    queryFn: () => cacheRemoteFile(`/compliance/${id}/file${version ? `?version=${version}` : ""}`, `doc-${id!.slice(0, 8)}-${version ?? 0}`),
    enabled: needsCopy,
    staleTime: 4 * 60_000,
    gcTime: 5 * 60_000,
  });
  const error = link.error ?? copy.error ?? null;
  return {
    uri: link.data?.url ?? copy.data?.uri ?? null,
    contentType: link.data?.content_type ?? copy.data?.contentType ?? null,
    fileName: link.data?.file_name ?? null,
    loading: enabled && !error && !(link.data?.url ?? copy.data?.uri),
    error: error as Error | null,
    retry: () => { void link.refetch(); if (needsCopy) void copy.refetch(); },
  };
}
