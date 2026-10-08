import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiBlob, apiRequest } from "@/services/api";
import { camelize } from "@/lib/camel";
import { pushToast } from "@/lib/toast";

export interface DocBrief {
  id: string;
  fileName: string;
  contentType: string;
  sizeBytes: number;
  uploadedAt: string;
  uploadedBy: string | null;
  dueDate: string | null;
  status: "PENDING" | "CLEARED" | null;
  overdue: boolean;
}

export type DocKind = "card" | "bill" | "payment";

/** Display names. "bill" is shown as the invoice. */
export const DOC_LABEL: Record<DocKind, string> = {
  card: "compliance card",
  bill: "invoice",
  payment: "payment proof",
};

export type ComplianceStatus = "PENDING" | "PARTIAL" | "COMPLETE";

export interface ComplianceRow {
  storeId: string;
  name: string;
  externalCode: string;
  platform: string | null;
  platformSlug: string | null;
  entity: string | null;
  state: string | null;
  city: string | null;
  regionName: string | null;
  vendorName: string | null;
  manager: string | null;
  status: ComplianceStatus;
  percent: number;
  card: DocBrief | null;
  bill: DocBrief | null; // the invoice
  payment: DocBrief | null; // proof of payment
}

export interface ComplianceKpis {
  total: number;
  cardLogged: number;
  cardMissing: number;
  invoiceLogged: number;
  invoiceMissing: number;
  paymentLogged: number;
  paymentMissing: number;
  compliancePercent: number;
}

export interface ComplianceOptions {
  regions: { id: string; name: string }[];
  cities: string[];
  managers: string[];
  hasUnassigned: boolean;
}

export interface ComplianceStorePage {
  month: string;
  monthLabel: string;
  months: string[];
  items: ComplianceRow[];
  total: number;
  page: number;
  pageSize: number;
  kpis: ComplianceKpis;
  options: ComplianceOptions;
}

export interface RepoFilters {
  month: string;
  partner: string;
  region: string;
  city: string;
  manager: string;
  missing: string;
  range: string;
  status: string;
  q: string;
  sort: string;
  dir: "asc" | "desc";
  page: number;
}

export interface BulkResult {
  kind: DocKind;
  month: string;
  filesReceived: number;
  filesMatched: number;
  storesUpdated: number;
  unmatched: string[];
  failed: { store: string; error: string }[];
}

export interface SearchRow {
  storeId: string;
  month: string;
  name: string;
  externalCode: string;
  platform: string | null;
  entity: string | null;
  state: string | null;
  city: string | null;
  vendorName: string | null;
  card: DocBrief | null;
  bill: DocBrief | null;
  payment: DocBrief | null;
}

export interface DueBill {
  id: string;
  storeId: string;
  storeName: string;
  externalCode: string;
  platform: string | null;
  entity: string | null;
  state: string | null;
  vendorName: string | null;
  month: string;
  dueDate: string;
  daysOverdue: number;
  fileName: string;
}

export interface SearchFilters {
  month: string;
  partner: string;
  entity: string;
  state: string;
  city: string;
  vendor: string;
  q: string;
  kind: "any" | "card" | "bill" | "payment" | "all";
}

function qs(obj: Record<string, string | number | undefined>): string {
  const p = new URLSearchParams();
  Object.entries(obj).forEach(([k, v]) => {
    if (v !== undefined && v !== "") p.set(k, String(v));
  });
  return p.toString();
}

export function useComplianceRepo(f: RepoFilters) {
  return useQuery({
    queryKey: ["compliance", "repo", f],
    queryFn: async () =>
      camelize<ComplianceStorePage>(
        await apiRequest(
          `/compliance/stores?${qs({
            month: f.month, partner: f.partner, region: f.region, city: f.city, manager: f.manager,
            missing: f.missing, range: f.range, status: f.status, q: f.q, sort: f.sort, dir: f.dir,
            page: f.page, page_size: 50,
          })}`,
        ),
      ),
    placeholderData: (prev) => prev,
  });
}

export function useComplianceSearch(f: SearchFilters, page: number) {
  return useQuery({
    queryKey: ["compliance", "search", f, page],
    queryFn: async () =>
      camelize<{ items: SearchRow[]; total: number; page: number; pageSize: number }>(
        await apiRequest(`/compliance/search?${qs({ ...f, page, page_size: 50 })}`),
      ),
    placeholderData: (prev) => prev,
  });
}

export function useDueBills() {
  return useQuery({
    queryKey: ["compliance", "due"],
    queryFn: async () => camelize<{ total: number; items: DueBill[] }>(await apiRequest("/compliance/due")),
  });
}

export function useUploadDoc() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (v: { storeId: string; month: string; kind: DocKind; files: File[] }) => {
      const body = new FormData();
      body.append("store_id", v.storeId);
      body.append("month", v.month);
      body.append("kind", v.kind);
      v.files.forEach((f) => body.append("files", f));
      return camelize<DocBrief>(await apiRequest("/compliance/upload", { method: "POST", body }));
    },
    onSuccess: (_d, v) => {
      qc.invalidateQueries({ queryKey: ["compliance"] });
      pushToast(`${DOC_LABEL[v.kind][0].toUpperCase()}${DOC_LABEL[v.kind].slice(1)} uploaded.`, "success");
    },
  });
}

export function useRemoveDoc() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => apiRequest<void>(`/compliance/${id}`, { method: "DELETE" }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["compliance"] });
      pushToast("Document removed.", "success");
    },
  });
}

export function useClearBill() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => apiRequest<unknown>(`/compliance/${id}/clear`, { method: "POST" }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["compliance"] });
      pushToast("Bill marked as cleared.", "success");
    },
  });
}

interface DocLink {
  url: string | null;
  contentType: string;
  fileName: string;
}

/** Ask the API for a short-lived direct link to the file (permission-checked). `url` is null on local-disk storage. */
async function documentLink(id: string): Promise<DocLink> {
  return camelize<DocLink>(await apiRequest(`/compliance/${id}/url`));
}

/** Open a stored document in a new tab. With bucket storage the browser loads it straight from the bucket
 * through a signed link, so the API never streams the bytes; on local-disk storage it falls back to /file. */
export async function openDocument(id: string): Promise<void> {
  const win = window.open("", "_blank"); // opened synchronously so popup blockers allow it
  try {
    const link = await documentLink(id);
    if (link.url) {
      if (win) win.location.href = link.url;
      else window.location.href = link.url;
      return;
    }
    const blob = await apiBlob(`/compliance/${id}/file`);
    const url = URL.createObjectURL(blob);
    if (win) win.location.href = url;
    else window.location.href = url;
    setTimeout(() => URL.revokeObjectURL(url), 5 * 60_000);
  } catch {
    win?.close();
  }
}

export async function downloadDocsZip(ids: string[]): Promise<void> {
  const blob = await apiBlob("/compliance/download", { method: "POST", body: { ids } });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "documents.zip";
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

/** Print photos from a clean window; PDFs can't be printed reliably from here, so they open in a tab instead. */
export async function printDocuments(ids: string[]): Promise<{ printed: number; opened: number }> {
  const docs = await Promise.all(
    ids.map(async (id) => {
      const link = await documentLink(id);
      // Direct signed link when the bucket offers one; otherwise fetch through the API and use a local blob URL.
      const src = link.url ?? URL.createObjectURL(await apiBlob(`/compliance/${id}/file`));
      return { src, isImage: link.contentType.startsWith("image/") };
    }),
  );
  const images = docs.filter((d) => d.isImage);
  const pdfs = docs.filter((d) => !d.isImage);
  if (images.length) {
    const w = window.open("", "_blank");
    if (w) {
      w.document.write(
        `<!doctype html><title>Print documents</title><style>body{margin:0}img{display:block;max-width:100%;max-height:100vh;margin:0 auto;page-break-after:always}</style>` +
          images.map((d) => `<img src="${d.src}">`).join(""),
      );
      w.document.close();
      w.onload = () => w.print();
    }
  }
  pdfs.slice(0, 5).forEach((d) => window.open(d.src, "_blank"));
  return { printed: images.length, opened: Math.min(pdfs.length, 5) };
}

export function useBulkUpload() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (v: { month: string; kind: DocKind; files: File[] }) => {
      const body = new FormData();
      body.append("month", v.month);
      body.append("kind", v.kind);
      v.files.forEach((f) => body.append("files", f));
      return camelize<BulkResult>(await apiRequest("/compliance/bulk", { method: "POST", body }));
    },
    onSuccess: (r) => {
      void qc.invalidateQueries({ queryKey: ["compliance"] });
      pushToast(`Bulk upload: ${r.storesUpdated} store${r.storesUpdated === 1 ? "" : "s"} updated.`, "success");
    },
  });
}

/** One collective PDF of the selected stores' cards, invoices and payment proofs (headed with outlet id + store name), opened in a new tab. */
export async function openSummaryPdf(storeIds: string[], month: string): Promise<void> {
  const win = window.open("", "_blank"); // opened synchronously so popup blockers allow it
  try {
    const blob = await apiBlob("/compliance/summary-pdf", { method: "POST", body: { store_ids: storeIds, month } });
    const url = URL.createObjectURL(blob);
    if (win) win.location.href = url;
    else window.location.href = url;
    setTimeout(() => URL.revokeObjectURL(url), 10 * 60_000);
  } catch {
    win?.close();
  }
}
