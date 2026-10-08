import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiBlob, apiRequest } from "@/services/api";
import { camelize } from "@/lib/camel";
import { pushToast } from "@/lib/toast";

export type ReportStatus = "VALID" | "EXPIRING" | "EXPIRED" | "MISSING";

export interface TestReportFile {
  id: string;
  periodStart: string;
  periodEnd: string;
  fileName: string;
  contentType: string;
  sizeBytes: number;
  uploadedAt: string;
  uploadedBy: string | null;
  /** Negative once the six months are over. */
  daysLeft: number;
  status: Exclude<ReportStatus, "MISSING">;
}

export interface StateReports {
  state: string;
  stores: number;
  status: ReportStatus;
  current: TestReportFile | null;
  history: TestReportFile[];
}

export interface PlatformFlag {
  slug: string;
  name: string;
  enabled: boolean;
}

export interface TestReportOverview {
  platform: PlatformFlag;
  platforms: PlatformFlag[];
  alertDays: number;
  summary: { statesTotal: number; valid: number; expiring: number; expired: number; missing: number; reportsTotal: number };
  states: StateReports[];
}

export const STATUS_LABEL: Record<ReportStatus, string> = {
  VALID: "Valid",
  EXPIRING: "Expiring soon",
  EXPIRED: "Expired",
  MISSING: "No report",
};

export function useTestReports(partner: string, enabled = true) {
  return useQuery({
    queryKey: ["test-reports", partner],
    queryFn: async () => camelize<TestReportOverview>(await apiRequest(`/test-reports?partner=${encodeURIComponent(partner)}`)),
    enabled: enabled && Boolean(partner),
    staleTime: 60_000,
  });
}

export function useUploadTestReport() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (v: { partner: string; state: string; periodStart: string; file: File }) => {
      const body = new FormData();
      body.append("partner", v.partner);
      body.append("state", v.state);
      body.append("period_start", v.periodStart);
      body.append("file", v.file);
      return camelize<TestReportFile>(await apiRequest("/test-reports", { method: "POST", body }));
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["test-reports"] });
      pushToast("Test report uploaded.", "success");
    },
  });
}

export function useRemoveTestReport() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => apiRequest<unknown>(`/test-reports/${id}`, { method: "DELETE" }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["test-reports"] });
      pushToast("Test report removed.", "success");
    },
  });
}

/** Open a report in a new tab — straight from the bucket via a signed link, or through the API on local-disk storage. */
export async function openTestReport(id: string): Promise<void> {
  const win = window.open("", "_blank"); // opened synchronously so popup blockers allow it
  try {
    const link = camelize<{ url: string | null }>(await apiRequest(`/test-reports/${id}/url`));
    if (link.url) {
      if (win) win.location.href = link.url;
      else window.location.href = link.url;
      return;
    }
    const url = URL.createObjectURL(await apiBlob(`/test-reports/${id}/file`));
    if (win) win.location.href = url;
    else window.location.href = url;
    setTimeout(() => URL.revokeObjectURL(url), 5 * 60_000);
  } catch {
    win?.close();
  }
}

/** "Oct 2026 – Mar 2027" for a period's two ISO dates. */
export function periodLabel(startIso: string, endIso: string): string {
  const f = (iso: string) => new Date(`${iso}T12:00:00`).toLocaleDateString(undefined, { month: "short", year: "numeric" });
  return `${f(startIso)} – ${f(endIso)}`;
}

/** The end of a 6-month period that starts in `yyyy-mm` (what the server will store). */
export function periodEndOf(yyyyMm: string): string {
  const [y, m] = yyyyMm.split("-").map(Number);
  if (!y || !m) return "";
  const idx = y * 12 + (m - 1) + 5;
  const ey = Math.floor(idx / 12);
  const em = (idx % 12) + 1;
  const last = new Date(ey, em, 0).getDate();
  return `${ey}-${String(em).padStart(2, "0")}-${String(last).padStart(2, "0")}`;
}
