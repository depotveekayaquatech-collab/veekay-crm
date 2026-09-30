import { useState } from "react";
import { Modal } from "@/components/ui/Modal";
import { Button } from "@/components/ui/Button";
import { Select } from "@/components/ui/Select";
import { FileDropzone } from "@/components/ui/FileDropzone";
import { IconCheckCircle, IconDownload } from "@/components/ui/icons";
import { downloadCsv } from "@/lib/csv";
import { usePartners } from "@/features/stores/useStores";
import { useImportOrders } from "@/features/orders/useOrders";
import type { OrderImportResult } from "@/types/order";

const ACCEPT = ".csv,.xlsx,.xlsm";
const MAX_MB = 10;

function downloadTemplate() {
  const d = (n: number) => {
    const x = new Date();
    x.setDate(x.getDate() - n);
    return new Date(x.getTime() - x.getTimezoneOffset() * 60000).toISOString().slice(0, 10);
  };
  downloadCsv(
    "order-sheet-template.csv",
    ["S.No", "Outlet ID", "Outlet Name", d(2), d(1), d(0)],
    [
      [1, "BLK-1001", "Example Store", 24, 0, 31],
      [2, "BLK-1002", "Another Store", 18, 22, ""],
    ],
  );
}

export function ImportOrdersModal({ onClose }: { onClose: () => void }) {
  const { data: partners = [] } = usePartners();
  const importOrders = useImportOrders();
  const [partner, setPartner] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [overwrite, setOverwrite] = useState(false);
  const [localError, setLocalError] = useState<string | null>(null);
  const [result, setResult] = useState<OrderImportResult | null>(null);

  const activePartner = partner || partners[0]?.slug || "";

  function pick(f: File | undefined) {
    setLocalError(null);
    setResult(null);
    if (!f) return;
    if (!/\.(csv|xlsx|xlsm)$/i.test(f.name)) return setLocalError("Please choose a .csv or .xlsx file.");
    if (f.size > MAX_MB * 1024 * 1024) return setLocalError(`That file is larger than ${MAX_MB} MB.`);
    setFile(f);
  }

  function submit() {
    if (!file || !activePartner) return;
    importOrders.mutate({ platform: activePartner, file, overwrite }, { onSuccess: setResult });
  }

  return (
    <Modal
      open
      onClose={onClose}
      title="Import order sheet"
      description="Bulk-mark bottle counts from a sheet with one row per store and one column per date."
      footer={
        result ? (
          <Button onClick={onClose}>Done</Button>
        ) : (
          <>
            <Button variant="secondary" onClick={onClose}>Cancel</Button>
            <Button onClick={submit} disabled={!file || !activePartner} isLoading={importOrders.isPending}>
              Upload &amp; import
            </Button>
          </>
        )
      }
    >
      {result ? (
        <div className="flex flex-col gap-4">
          <div className="flex items-center gap-3 rounded-xl bg-status-success-soft px-4 py-3 text-status-success">
            <IconCheckCircle className="h-6 w-6 shrink-0" />
            <div>
              <p className="text-sm font-bold">Order sheet imported</p>
              <p className="text-xs opacity-80">
                {result.rowsRead} store rows from {result.sheets.length} sheet{result.sheets.length === 1 ? "" : "s"}
              </p>
            </div>
          </div>
          <div className="grid grid-cols-3 gap-3 text-center">
            {[
              { l: "Added", v: result.created, c: "text-status-success" },
              { l: "Updated", v: result.updated, c: "text-brand-600" },
              { l: "Unchanged", v: result.unchanged, c: "text-gray-600" },
            ].map((x) => (
              <div key={x.l} className="rounded-xl border border-surface-border p-3">
                <p className={`text-2xl font-bold tabular-nums ${x.c}`}>{x.v}</p>
                <p className="text-[11px] font-bold uppercase tracking-wider text-gray-500">{x.l}</p>
              </div>
            ))}
          </div>
          {result.sheets.length > 0 && (
            <p className="text-xs text-gray-500">Sheets used: {result.sheets.join(", ")}</p>
          )}
          {result.warnings.length > 0 && (
            <ul className="list-disc space-y-1 rounded-lg bg-status-warning-soft px-4 py-2.5 pl-8 text-xs text-status-warning">
              {result.warnings.map((w, i) => (
                <li key={i}>{w}</li>
              ))}
            </ul>
          )}
          <p className="text-xs text-gray-500">Calendars, the dashboard and reports have been refreshed.</p>
        </div>
      ) : (
        <div className="flex flex-col gap-4">
          <Select
            label="Platform"
            value={activePartner}
            onChange={(e) => setPartner(e.target.value)}
            options={partners.map((p) => ({ value: p.slug, label: p.name }))}
          />

          <FileDropzone file={file} onPick={pick} accept={ACCEPT} hint={`.csv or .xlsx · up to ${MAX_MB} MB`} />

          <label className="flex cursor-pointer items-start gap-2.5 rounded-lg border border-surface-border px-3.5 py-3 text-sm">
            <input
              type="checkbox"
              checked={overwrite}
              onChange={(e) => setOverwrite(e.target.checked)}
              className="mt-0.5 accent-brand-500"
            />
            <span>
              <span className="font-semibold text-gray-800">Overwrite existing entries</span>
              <span className="block text-xs text-gray-500">
                Off (default): days that already have a different count are left alone. On: the sheet replaces them.
              </span>
            </span>
          </label>

          {(localError || importOrders.error) && (
            <p role="alert" className="rounded-lg bg-status-danger-soft px-3 py-2 text-sm text-status-danger">
              {localError ?? (importOrders.error instanceof Error ? importOrders.error.message : "Import failed.")}
            </p>
          )}

          <div className="flex items-start justify-between gap-3 rounded-lg bg-surface-subtle px-3.5 py-3 text-xs text-gray-600">
            <p>
              Needs an <b>Outlet ID</b> column and one column per date (e.g. <b>2026-09-01</b>). Blank = not marked, <b>0</b> = marked with
              zero. Stores must already exist — import them first. In an Excel workbook every tab with these columns is read; other tabs
              are ignored.
            </p>
            <button onClick={downloadTemplate} className="flex shrink-0 items-center gap-1 font-semibold text-brand-600 hover:text-brand-700">
              <IconDownload className="h-3.5 w-3.5" /> Template
            </button>
          </div>
        </div>
      )}
    </Modal>
  );
}
