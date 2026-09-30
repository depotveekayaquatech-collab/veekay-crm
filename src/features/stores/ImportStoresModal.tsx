import { useState } from "react";
import { Modal } from "@/components/ui/Modal";
import { Button } from "@/components/ui/Button";
import { Select } from "@/components/ui/Select";
import { FileDropzone } from "@/components/ui/FileDropzone";
import { IconCheckCircle, IconDownload } from "@/components/ui/icons";
import { downloadCsv } from "@/lib/csv";
import { useStoreMutations, usePartners } from "@/features/stores/useStores";
import type { StoreSyncResult } from "@/types/store";

const ACCEPT = ".csv,.xlsx,.xlsm";
const MAX_MB = 5;

// Same columns as the Blinkit outlet sheet. Login / password columns are
// accepted in an uploaded file but always ignored, so the template omits them.
const TEMPLATE_HEADER = [
  "S.NO", "Entity", "ZONE", "State", "City", "Outlet ID", "Outlet Name", "STATUS", "Rate - BCPL",
  "DATE RECEIVED", "START DATE BY BLINKIT", "start Date", "Address", "POC Name", "POC Contact no",
  "MAIL ID POC", "vendor", "Contact Details", "location",
];

function downloadTemplate() {
  downloadCsv("blinkit-stores-template.csv", TEMPLATE_HEADER, [
    [1, "Blinkit", "North Zone", "Delhi", "Delhi", "BLK-1001", "Blinkit - Example", "Live", "", "", "", "", "Sector 1, Rohini", "Store Manager", "9999999999", "", "Local Vendor", "8888888888", "Rohini"],
  ]);
}

export function ImportStoresModal({ onClose }: { onClose: () => void }) {
  const { data: partners = [] } = usePartners();
  const { importFile } = useStoreMutations();
  const [partner, setPartner] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [localError, setLocalError] = useState<string | null>(null);
  const [result, setResult] = useState<StoreSyncResult | null>(null);

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
    importFile.mutate({ platform: activePartner, file }, { onSuccess: setResult });
  }

  const done = result !== null;

  return (
    <Modal
      open
      onClose={onClose}
      title="Import stores from a file"
      description="Upload an outlet list — stores are added or updated, never deleted."
      footer={
        done ? (
          <Button onClick={onClose}>Done</Button>
        ) : (
          <>
            <Button variant="secondary" onClick={onClose}>Cancel</Button>
            <Button onClick={submit} disabled={!file || !activePartner} isLoading={importFile.isPending}>
              Upload &amp; import
            </Button>
          </>
        )
      }
    >
      {done && result ? (
        <div className="flex flex-col gap-4">
          <div className="flex items-center gap-3 rounded-xl bg-status-success-soft px-4 py-3 text-status-success">
            <IconCheckCircle className="h-6 w-6 shrink-0" />
            <div>
              <p className="text-sm font-bold">Import complete</p>
              <p className="text-xs opacity-80">{result.rowsRead} rows read from {file?.name}</p>
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
          {result.warnings.length > 0 && (
            <details className="rounded-lg bg-status-warning-soft px-3 py-2 text-xs text-status-warning">
              <summary className="cursor-pointer font-semibold">
                {result.warnings.length} note{result.warnings.length > 1 ? "s" : ""}
              </summary>
              <ul className="mt-1.5 max-h-36 list-disc overflow-auto pl-4">
                {result.warnings.map((w, i) => (
                  <li key={i}>{w}</li>
                ))}
              </ul>
            </details>
          )}
          <p className="text-xs text-gray-500">The store list and dashboard have been refreshed with the new data.</p>
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

          {(localError || importFile.error) && (
            <p role="alert" className="rounded-lg bg-status-danger-soft px-3 py-2 text-sm text-status-danger">
              {localError ?? (importFile.error instanceof Error ? importFile.error.message : "Import failed.")}
            </p>
          )}

          <div className="flex items-start justify-between gap-3 rounded-lg bg-surface-subtle px-3.5 py-3 text-xs text-gray-600">
            <p>
              Use your outlet-sheet format (first row = headers). Read: <b>Outlet ID</b>, <b>Outlet Name</b>, ZONE, State, City,
              STATUS, start Date, Address, POC Name, POC Contact no, vendor, Contact Details. Other columns (and any login / password columns)
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
