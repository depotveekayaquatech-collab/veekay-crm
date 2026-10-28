import { useState } from "react";
import { IconDownload } from "@/components/ui/icons";
import { pushToast } from "@/lib/toast";
import { apiBlob } from "@/services/api";

export type TemplateKind = "orders" | "employees" | "attendance" | "cash" | "cardsheet" | "stores" | "vendor-rates";

/**
 * "Download template": an Excel file in exactly the format the upload next to it reads (sample rows and a "How to fill" tab), so a sheet can be shaped to match
 * BEFORE it is uploaded. `month` (YYYY-MM) sets the date columns for the order and attendance sheets.
 */
export function TemplateLink({ kind, month, label = "Template", className = "" }: { kind: TemplateKind; month?: string; label?: string; className?: string }) {
  const [busy, setBusy] = useState(false);

  async function download() {
    setBusy(true);
    try {
      const blob = await apiBlob(`/templates/${kind}${month ? `?month=${encodeURIComponent(month)}` : ""}`);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${kind}-template${month ? `-${month}` : ""}.xlsx`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 30_000);
    } catch {
      pushToast("Couldn't download the template. Try again.", "error");
    } finally {
      setBusy(false);
    }
  }

  return (
    <button
      type="button"
      onClick={() => void download()}
      disabled={busy}
      className={`flex shrink-0 items-center gap-1 text-sm font-semibold text-brand-600 hover:text-brand-700 disabled:opacity-60 ${className}`}
    >
      <IconDownload className="h-3.5 w-3.5" aria-hidden="true" />
      {busy ? "Preparing…" : label}
    </button>
  );
}
