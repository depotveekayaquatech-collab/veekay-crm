/**
 * The EXISTING compliance API (the same routes the web CRM's Compliance tab uses). Nothing here is new on the server:
 * the server decides what each employee may see and do (their own stores; admins any), so hiding a button is never the security.
 */
import { request, requestUpload, type UploadOptions } from "@/api/client";
import type { ComplianceStatus, DocKind, UploadPolicy } from "@/lib/compliance";

export interface DocBrief {
  id: string;
  file_name: string;
  content_type: string;
  size_bytes: number;
  uploaded_at: string;
  uploaded_by: string | null;
  due_date: string | null;
  status: string | null;
  overdue: boolean;
}

export interface ComplianceRow {
  store_id: string;
  name: string;
  external_code: string;
  platform: string | null;
  entity: string | null;
  state: string | null;
  city: string | null;
  region_name: string | null;
  vendor_name: string | null;
  manager: string | null;
  status: ComplianceStatus;
  percent: number;
  card: DocBrief | null;
  bill: DocBrief | null;
  payment: DocBrief | null;
}

export interface ComplianceKpis {
  total: number;
  card_logged: number;
  card_missing: number;
  invoice_logged: number;
  invoice_missing: number;
  payment_logged: number;
  payment_missing: number;
  compliance_percent: number;
}

export interface CompliancePage {
  month: string;            // YYYY-MM
  month_label: string;
  months: string[];         // the months that can be chosen, newest first
  items: ComplianceRow[];
  total: number;
  page: number;
  page_size: number;
  kpis: ComplianceKpis;
}

export interface DocVersion {
  version: number;
  file_name: string;
  size_bytes: number;
  content_type: string;
  uploaded_at: string;
  source_files: number;
  current: boolean;
}

export interface DocLink {
  url: string | null;       // a short-lived direct link; null when the server streams the file instead
  content_type: string;
  file_name: string;
  expires_in: number;
}

export interface ComplianceQuery {
  month?: string;
  q?: string;
  status?: ComplianceStatus;
  missing?: "any" | DocKind;
  page?: number;
  page_size?: number;
}

function qs(p: Record<string, string | number | undefined>): string {
  const u = new URLSearchParams();
  for (const [k, v] of Object.entries(p)) if (v !== undefined && v !== "") u.set(k, String(v));
  const s = u.toString();
  return s ? `?${s}` : "";
}

export const complianceApi = {
  /** The monthly list: the employee's own stores (the server scopes it), with the card, invoice and payment proof of each. */
  stores: (p: ComplianceQuery) => request<CompliancePage>(`/compliance/stores${qs({ ...p, page_size: p.page_size ?? 25 })}`),
  versions: (id: string) => request<DocVersion[]>(`/compliance/${id}/versions`),
  link: (id: string, version?: number) => request<DocLink>(`/compliance/${id}/url${qs({ version })}`),
  /** Archives (hides) the document, exactly like the web page: the file stays in storage and uploading again brings it back. */
  remove: (id: string) => request<void>(`/compliance/${id}`, { method: "DELETE" }),
  /** The upload limits the server enforces. */
  policy: () => request<UploadPolicy>("/uploads/policy"),
  /** One document for one store, month and kind. One photo is stored as it is (shrunk by the server), several are merged into one PDF. */
  upload: (form: FormData, o: UploadOptions) => requestUpload<DocBrief>("/compliance/upload", form, o),
};
