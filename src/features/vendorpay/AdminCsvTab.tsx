import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { FileDropzone } from "@/components/ui/FileDropzone";
import { Select } from "@/components/ui/Select";
import { Skeleton } from "@/components/feedback/Skeleton";
import { downloadCsvTemplate, previewCsv, useImportCsv, type CsvPreview, type SyncResult } from "@/features/vendorpay/adminApi";
import { SyncResultPanel } from "@/features/vendorpay/SyncResultPanel";
import { pushToast } from "@/lib/toast";

const FIELDS: { key: string; label: string; required: boolean }[] = [
  { key: "date", label: "Date", required: true },
  { key: "type", label: "Type (BILL or PAYMENT)", required: true },
  { key: "amount", label: "Amount", required: true },
  { key: "voucher_no", label: "Voucher number", required: true },
  { key: "vendor_code", label: "Vendor code", required: false },
  { key: "account_name", label: "Account name (code at the end)", required: false },
  { key: "narration", label: "Narration", required: false },
];
const NOT_IN_FILE = "(not in this file)";

type Mapping = Record<string, string | null>;

export function AdminCsvTab() {
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<CsvPreview | null>(null);
  const [mapping, setMapping] = useState<Mapping>({});
  const [checking, setChecking] = useState(false);
  const [imported, setImported] = useState<SyncResult | null>(null);
  const importCsv = useImportCsv();

  async function check(next: File, chosen: Mapping | null) {
    setChecking(true);
    try {
      const p = await previewCsv(next, chosen);
      setPreview(p);
      setMapping(p.mapping);
    } catch {
      setPreview(null); // the API layer already showed the reason
    } finally {
      setChecking(false);
    }
  }

  function pick(next: File | undefined) {
    if (!next) return;
    if (!/\.(csv|txt)$/i.test(next.name)) {
      pushToast("Choose a .csv file (in Excel: Save As, CSV).", "error");
      return;
    }
    setFile(next);
    setImported(null);
    void check(next, null);
  }

  function remap(field: string, header: string) {
    const next = { ...mapping, [field]: header || null };
    setMapping(next);
    if (file) void check(file, next);
  }

  async function runImport() {
    if (!file) return;
    try {
      setImported(await importCsv.mutateAsync({ file, mapping }));
      setPreview(null);
      setFile(null);
      pushToast("Import finished.", "success");
    } catch {
      /* the API layer already showed the reason */
    }
  }

  const result = preview?.result ?? null;
  const importable = result ? result.inserted + result.updated + result.unmatched : 0;
  const options = (preview?.headers ?? []).map((h) => ({ value: h, label: h }));

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="max-w-2xl text-sm text-gray-600">
          Upload a CSV of bills and payments from Busy. You see exactly what would be added, updated and rejected before anything is saved. Vendors are matched by vendor code only.
        </p>
        <Button variant="secondary" onClick={() => void downloadCsvTemplate()}>
          Download sample CSV
        </Button>
      </div>

      <FileDropzone file={file} onPick={pick} accept=".csv,text/csv" hint="Drop a CSV file here, or click to choose" />

      {checking && <Skeleton className="h-24 w-full" />}

      {preview && !checking && (
        <>
          <section className="flex flex-col gap-3">
            <h3 className="text-sm font-bold text-heading">Columns ({preview.totalRows.toLocaleString("en-IN")} data rows)</h3>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {FIELDS.map((f) => (
                <Select
                  key={f.key}
                  label={f.required ? `${f.label} *` : f.label}
                  value={mapping[f.key] ?? ""}
                  options={options}
                  placeholder={NOT_IN_FILE}
                  onChange={(e) => remap(f.key, e.target.value)}
                />
              ))}
            </div>
            {preview.missingFields.length > 0 && (
              <p role="alert" className="rounded-xl bg-status-warning-soft px-4 py-3 text-sm text-status-warning">
                Choose a column for: {preview.missingFields.join(", ")}.
              </p>
            )}
          </section>

          {result && (
            <section className="flex flex-col gap-3">
              <h3 className="text-sm font-bold text-heading">Dry run: nothing is saved yet</h3>
              <SyncResultPanel result={result} dryRun />
              <div className="flex flex-wrap items-center gap-3">
                <Button isLoading={importCsv.isPending} disabled={importable === 0} onClick={() => void runImport()}>
                  Import {importable.toLocaleString("en-IN")} rows
                </Button>
                {result.rejected > 0 && <span className="text-xs text-gray-500">The {result.rejected} rejected rows will be skipped.</span>}
              </div>
            </section>
          )}
        </>
      )}

      {imported && (
        <section className="flex flex-col gap-3">
          <h3 className="text-sm font-bold text-heading">Import finished</h3>
          <SyncResultPanel result={imported} dryRun={false} />
        </section>
      )}
    </div>
  );
}
