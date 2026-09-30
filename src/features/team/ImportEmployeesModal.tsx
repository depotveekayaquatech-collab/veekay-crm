import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Modal } from "@/components/ui/Modal";
import { Button } from "@/components/ui/Button";
import { FileDropzone } from "@/components/ui/FileDropzone";
import { IconCheckCircle, IconDownload } from "@/components/ui/icons";
import { downloadCsv } from "@/lib/csv";
import { pushToast } from "@/lib/toast";
import { apiRequest } from "@/services/api";

interface ImportResult {
  created: number;
  updated: number;
  unchanged: number;
  skipped: number;
  assignments: number;
  credentials: { employee_code: string; full_name: string; temp_password: string }[];
  warnings: string[];
}

const ACCEPT = ".csv,.xlsx,.xlsm";
const MAX_MB = 5;

export function ImportEmployeesModal({ onClose }: { onClose: () => void }) {
  const qc = useQueryClient();
  const [file, setFile] = useState<File | null>(null);
  const [keepPasswords, setKeepPasswords] = useState(false);
  const [localError, setLocalError] = useState<string | null>(null);
  const [result, setResult] = useState<ImportResult | null>(null);

  const run = useMutation({
    mutationFn: async () => {
      const body = new FormData();
      body.append("file", file as File);
      body.append("keep_sheet_passwords", String(keepPasswords));
      return apiRequest<ImportResult>("/employees/import", { method: "POST", body });
    },
    onSuccess: (r) => {
      setResult(r);
      qc.invalidateQueries({ queryKey: ["employees"] });
      qc.invalidateQueries({ queryKey: ["state-board"] });
      pushToast(`Employees imported — ${r.created} added, ${r.updated} updated.`, "success");
    },
  });

  function pick(f: File | undefined) {
    setLocalError(null);
    if (!f) return;
    if (!/\.(csv|xlsx|xlsm)$/i.test(f.name)) return setLocalError("Please choose a .csv or .xlsx file.");
    if (f.size > MAX_MB * 1024 * 1024) return setLocalError(`That file is larger than ${MAX_MB} MB.`);
    setFile(f);
  }

  return (
    <Modal
      open
      onClose={onClose}
      title="Import employees"
      description="Bring people over from the old EMPLOYEES sheet."
      footer={
        result ? (
          <Button onClick={onClose}>Done</Button>
        ) : (
          <>
            <Button variant="secondary" onClick={onClose}>Cancel</Button>
            <Button onClick={() => run.mutate()} disabled={!file} isLoading={run.isPending}>
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
            <p className="text-sm font-bold">Import complete</p>
          </div>
          <div className="grid grid-cols-2 gap-3 text-center sm:grid-cols-4">
            {[
              { l: "Added", v: result.created, c: "text-status-success" },
              { l: "Updated", v: result.updated, c: "text-brand-600" },
              { l: "Unchanged", v: result.unchanged, c: "text-gray-600" },
              { l: "State links", v: result.assignments, c: "text-aqua-600" },
            ].map((x) => (
              <div key={x.l} className="rounded-xl border border-surface-border p-3">
                <p className={`text-2xl font-bold tabular-nums ${x.c}`}>{x.v}</p>
                <p className="text-[11px] font-bold uppercase tracking-wider text-gray-500">{x.l}</p>
              </div>
            ))}
          </div>

          {result.credentials.length > 0 && (
            <div className="rounded-xl border border-status-warning/30 bg-status-warning-soft px-4 py-3">
              <p className="text-sm font-bold text-status-warning">Temporary passwords were generated</p>
              <p className="mt-1 text-xs text-gray-700">
                They are shown only now and are not stored anywhere readable. Download them and share each one with its employee.
              </p>
              <Button
                size="sm"
                className="mt-2.5"
                onClick={() =>
                  downloadCsv(
                    "employee-temporary-passwords.csv",
                    ["Employee ID", "Name", "Temporary password"],
                    result.credentials.map((c) => [c.employee_code, c.full_name, c.temp_password]),
                  )
                }
              >
                <IconDownload className="h-3.5 w-3.5" />
                Download {result.credentials.length} password{result.credentials.length > 1 ? "s" : ""} (CSV)
              </Button>
            </div>
          )}

          {result.warnings.length > 0 && (
            <ul className="max-h-36 list-disc space-y-1 overflow-auto rounded-lg bg-surface-subtle px-4 py-2.5 pl-8 text-xs text-gray-600">
              {result.warnings.map((w, i) => (
                <li key={i}>{w}</li>
              ))}
            </ul>
          )}
        </div>
      ) : (
        <div className="flex flex-col gap-4">
          <FileDropzone file={file} onPick={pick} accept={ACCEPT} hint={`.xlsx workbook or .csv · up to ${MAX_MB} MB`} />

          <label className="flex cursor-pointer items-start gap-2.5 rounded-lg border border-surface-border px-3.5 py-3 text-sm">
            <input type="checkbox" checked={keepPasswords} onChange={(e) => setKeepPasswords(e.target.checked)} className="mt-0.5 accent-brand-500" />
            <span>
              <span className="font-semibold text-gray-800">Keep the passwords from the sheet</span>
              <span className="block text-xs text-gray-500">
                Off (recommended): new people get a generated temporary password. On: the sheet password is hashed on import so they
                can sign in as before. Existing users&apos; passwords are never changed.
              </span>
            </span>
          </label>

          {(localError || run.error) && (
            <p role="alert" className="rounded-lg bg-status-danger-soft px-3 py-2 text-sm text-status-danger">
              {localError ?? (run.error instanceof Error ? run.error.message : "Import failed.")}
            </p>
          )}

          <p className="rounded-lg bg-surface-subtle px-3.5 py-3 text-xs text-gray-600">
            Reads the <b>EMPLOYEES</b> tab: Employee ID, Employee Name, Password, Region, Status, IsAdmin, Platform, IsAccountant and a
            phone column. A <b>State_Assignments</b> tab (Zepto) is applied too. All other tabs are ignored and never read.
          </p>
        </div>
      )}
    </Modal>
  );
}
