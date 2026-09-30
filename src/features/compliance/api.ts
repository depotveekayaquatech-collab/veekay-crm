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

export interface ComplianceStoreRow {
  storeId: string;
  name: string;
  externalCode: string;
  platform: string | null;
  platformSlug: string | null;
  entity: string | null;
  state: string | null;
  city: string | null;
  vendorName: string | null;
  card: DocBrief | null;
  bill: DocBrief | null;
}

export interface ComplianceStorePage {
  month: string;
  monthLabel: string;
  months: string[];
  items: ComplianceStoreRow[];
  total: number;
  page: number;
  pageSize: number;
  cardsDone: number;
  billsDone: number;
  billsPending: number;
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
  kind: "any" | "card" | "bill" | "both";
}

function qs(obj: Record<string, string | number | undefined>): string {
  const p = new URLSearchParams();
  Object.entries(obj).forEach(([k, v]) => {
    if (v !== undefined && v !== "") p.set(k, String(v));
  });
  return p.toString();
}

export function useComplianceStores(params: { month: string; partner: string; q: string; page: number }) {
  return useQuery({
    queryKey: ["compliance", "stores", params],
    queryFn: async () =>
      camelize<ComplianceStorePage>(
        await apiRequest(
          `/compliance/stores?${qs({ month: params.month, partner: params.partner, q: params.q, page: params.page, page_size: 50 })}`,
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
    mutationFn: async (v: { storeId: string; month: string; kind: "card" | "bill"; files: File[] }) => {
      const body = new FormData();
      body.append("store_id", v.storeId);
      body.append("month", v.month);
      body.append("kind", v.kind);
      v.files.forEach((f) => body.append("files", f));
      return camelize<DocBrief>(await apiRequest("/compliance/upload", { method: "POST", body }));
    },
    onSuccess: (_d, v) => {
      qc.invalidateQueries({ queryKey: ["compliance"] });
      pushToast(v.kind === "card" ? "Card uploaded." : "Bill uploaded.", "success");
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

/** Open a stored document in a new tab (fetched with the auth header, so no public URL exists). */
export async function openDocument(id: string): Promise<void> {
  const win = window.open("", "_blank"); // opened synchronously so popup blockers allow it
  try {
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
  const blobs = await Promise.all(ids.map(async (id) => ({ id, blob: await apiBlob(`/compliance/${id}/file`) })));
  const images = blobs.filter((b) => b.blob.type.startsWith("image/"));
  const pdfs = blobs.filter((b) => !b.blob.type.startsWith("image/"));
  if (images.length) {
    const w = window.open("", "_blank");
    if (w) {
      const urls = images.map((b) => URL.createObjectURL(b.blob));
      w.document.write(
        `<!doctype html><title>Print documents</title><style>body{margin:0}img{display:block;max-width:100%;max-height:100vh;margin:0 auto;page-break-after:always}</style>` +
          urls.map((u) => `<img src="${u}">`).join(""),
      );
      w.document.close();
      w.onload = () => w.print();
    }
  }
  pdfs.slice(0, 5).forEach((b) => window.open(URL.createObjectURL(b.blob), "_blank"));
  return { printed: images.length, opened: Math.min(pdfs.length, 5) };
}
