import { useRef, useState } from "react";
import { TemplateLink } from "@/components/ui/TemplateLink";
import { useQueryClient } from "@tanstack/react-query";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import { apiRequest } from "@/services/api";
import { pushToast } from "@/lib/toast";

interface Preview {
  applied: boolean;
  month: string;
  sheet: string;
  people: number;
  days_in_sheet: number[];
  present_cells: number;
  will_create: number;
  will_overwrite: number;
  already_from_sheet: number;
  overwriting: { employee_code: string; full_name: string; date: string; was: { source: string; late: boolean; check_in_at: string | null; check_out_at: string | null } }[];
  overwriting_total: number;
  unmatched: { row: number; id: string | null; name: string | null }[];
  unmatched_total: number;
  skipped: { row: number; id: string | null; name: string | null; reason: string }[];
  skipped_total: number;
  ignored_cells: Record<string, number>;
  future_days_skipped: number;
}

const field = "h-10 rounded-lg border border-surface-border bg-surface px-3 text-sm shadow-sm outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20";

/** Developer only: fill a month from an attendance sheet. Always previews first; nothing is written until "Save to attendance". */
export function ImportSheetModal({ month: initialMonth, onClose }: { month: string; onClose: () => void }) {
  const qc = useQueryClient();
  const [month, setMonth] = useState(initialMonth);
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const input = useRef<HTMLInputElement>(null);

  async function send(apply: boolean) {
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      const body = new FormData();
      body.append("month", month);
      body.append("apply", apply ? "true" : "false");
      body.append("file", file);
      const r = await apiRequest<Preview>("/attendance/import", { method: "POST", body, silent: true });
      setPreview(r);
      if (apply) {
        pushToast(`Saved: ${r.will_create} new day${r.will_create === 1 ? "" : "s"}, ${r.will_overwrite} overwritten.`, "success");
        void qc.invalidateQueries({ queryKey: ["attendance"] });
        onClose();
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't read the sheet.");
      if (!apply) setPreview(null);
    } finally {
      setBusy(false);
    }
  }

  const nothing = preview !== null && preview.will_create + preview.will_overwrite === 0;

  return (
    <Modal
      open
      onClose={onClose}
      size="lg"
      title="Import attendance sheet"
      description="One row per employee (Employee ID), one column per day, P = present."
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={busy}>Cancel</Button>
          {preview && !nothing ? (
            <Button variant="danger" isLoading={busy} onClick={() => void send(true)}>
              Save to attendance{preview.will_overwrite ? ` (overwrites ${preview.will_overwrite})` : ""}
            </Button>
          ) : (
            <Button isLoading={busy} disabled={!file} onClick={() => void send(false)}>Preview</Button>
          )}
        </>
      }
    >
      <div className="flex flex-col gap-4 text-sm">
        <div className="flex flex-wrap items-end gap-3">
          <label className="flex flex-col gap-1.5 text-[13px] font-semibold text-gray-700">
            Month
            <input type="month" className={field} value={month} onChange={(e) => { setMonth(e.target.value); setPreview(null); }} />
          </label>
          <label className="flex min-w-[14rem] flex-1 flex-col gap-1.5 text-[13px] font-semibold text-gray-700">
            Sheet (.xlsx or .csv)
            <input
              ref={input}
              type="file"
              accept=".xlsx,.xlsm,.csv"
              className={`${field} py-1.5`}
              onChange={(e) => { setFile(e.target.files?.[0] ?? null); setPreview(null); setError(null); }}
            />
          </label>
        </div>
        <TemplateLink kind="attendance" month={month} label={`Download the sheet layout for ${month}`} />
        <ul className="list-disc space-y-0.5 pl-5 text-xs text-gray-500">
          <li>The first row needs <b>Employee ID</b> (and may have a Name) and the day numbers 1, 2, 3… as columns.</li>
          <li>Only <b>P</b> writes a day. Blank and A leave the day as it is. Days before today only.</li>
          <li>A day that already has a record is <b>overwritten</b>; what it held is kept in the activity log. These days do <b>not</b> go to salary.</li>
        </ul>

        {error && <p role="alert" className="rounded-lg bg-status-danger-soft px-3 py-2 text-status-danger">{error}</p>}

        {preview && (
          <div className="flex flex-col gap-3">
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
              {[
                ["People matched", preview.people],
                ["New days", preview.will_create],
                ["Overwritten", preview.will_overwrite],
                ["Already from a sheet", preview.already_from_sheet],
              ].map(([label, n]) => (
                <div key={label as string} className="rounded-xl bg-surface-subtle px-3 py-2.5">
                  <p className="text-[11px] font-semibold text-gray-500">{label}</p>
                  <p className="text-xl font-extrabold tabular-nums text-heading">{n}</p>
                </div>
              ))}
            </div>
            <p className="text-xs text-gray-500">
              Days found in the sheet: {preview.days_in_sheet[0]} to {preview.days_in_sheet[preview.days_in_sheet.length - 1]}, sheet "{preview.sheet}"
              {preview.future_days_skipped ? ` · ${preview.future_days_skipped} day(s) today or later skipped` : ""}
            </p>
            {nothing && <p className="rounded-lg bg-surface-subtle px-3 py-2 text-gray-600">Nothing to write: every P in this sheet is already recorded from a sheet, or none matched.</p>}

            {preview.unmatched_total > 0 && (
              <div className="rounded-xl border border-status-danger/30 p-3">
                <p className="mb-1 font-semibold text-status-danger">{preview.unmatched_total} row(s) not found in the CRM (nothing written for them)</p>
                <p className="text-xs text-gray-600">{preview.unmatched.map((u) => `row ${u.row}: ${u.id ?? u.name}`).join(" · ")}{preview.unmatched_total > preview.unmatched.length ? " · …" : ""}</p>
              </div>
            )}
            {preview.skipped_total > 0 && (
              <div className="rounded-xl border border-status-warning/30 p-3">
                <p className="mb-1 font-semibold text-status-warning">{preview.skipped_total} row(s) skipped</p>
                <ul className="space-y-0.5 text-xs text-gray-600">
                  {preview.skipped.map((s) => <li key={s.row}>row {s.row} ({s.id ?? s.name}): {s.reason}</li>)}
                </ul>
              </div>
            )}
            {Object.keys(preview.ignored_cells).length > 0 && (
              <p className="flex flex-wrap items-center gap-1.5 text-xs text-gray-600">
                Cells with other letters, left alone:
                {Object.entries(preview.ignored_cells).map(([k, n]) => <Badge key={k} tone="neutral">{k} × {n}</Badge>)}
              </p>
            )}
            {preview.overwriting_total > 0 && (
              <details className="rounded-xl border border-surface-border p-3">
                <summary className="cursor-pointer font-semibold text-heading">{preview.overwriting_total} existing day(s) will be overwritten</summary>
                <ul className="mt-2 max-h-48 space-y-0.5 overflow-auto text-xs text-gray-600">
                  {preview.overwriting.map((o, i) => (
                    <li key={i}>
                      {o.full_name} ({o.employee_code}) · {o.date} · was {o.was.check_in_at ? new Date(o.was.check_in_at).toLocaleTimeString("en-IN", { timeZone: "Asia/Kolkata", hour: "2-digit", minute: "2-digit" }) : "—"}
                      {o.was.late ? " (late)" : ""}
                    </li>
                  ))}
                  {preview.overwriting_total > preview.overwriting.length && <li>… and {preview.overwriting_total - preview.overwriting.length} more</li>}
                </ul>
              </details>
            )}
          </div>
        )}
      </div>
    </Modal>
  );
}
