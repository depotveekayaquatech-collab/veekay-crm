import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Modal } from "@/components/ui/Modal";
import { Table, Td, TableEmpty, Th } from "@/components/ui/Table";
import { camelize } from "@/lib/camel";
import { daysAgo } from "@/lib/dates";
import { pushToast } from "@/lib/toast";
import { apiRequest } from "@/services/api";

type Kind = "MISSING" | "CLEARED" | "CHANGED" | "HIDDEN_NOT_LIVE";

interface AuditRow {
  kind: Kind;
  reason?: string;
  orderDate: string;
  storeCode: string | null;
  storeName: string | null;
  state: string | null;
  employee: string | null;
  loggedCount: number | null;
  currentCount: number | null;
  storeStatus?: string;
  restorable: boolean;
  detail: string;
}

interface AuditReport {
  start: string;
  end: string;
  summary: { logged: number; ok: number; missing: number; cleared: number; changed: number; hiddenNotLive: number };
  rows: AuditRow[];
  truncated: boolean;
}

interface RestoreResult {
  restorable: number;
  restored: number;
  dryRun: boolean;
  examples: string[];
}

const BASE = "/developer/order-audit";
const KIND: Record<Kind, { label: string; tone: "danger" | "warning" | "info" | "neutral" }> = {
  MISSING: { label: "Missing", tone: "danger" },
  HIDDEN_NOT_LIVE: { label: "Store not live", tone: "warning" },
  CHANGED: { label: "Changed", tone: "info" },
  CLEARED: { label: "Cleared by admin", tone: "neutral" },
};
const day = (iso: string) => new Date(`${iso}T00:00:00`).toLocaleDateString("en-IN", { day: "2-digit", month: "short" });

/** Developer: what employees submitted (the audit log) against what is stored and visible, why any entry is missing or hidden, and the repair. */
export function EntryAudit() {
  const [start, setStart] = useState(daysAgo(3));
  const [end, setEnd] = useState(daysAgo(0));
  const [report, setReport] = useState<AuditReport | null>(null);
  const [confirm, setConfirm] = useState<RestoreResult | null>(null);

  const run = useMutation({
    mutationFn: async () => camelize<AuditReport>(await apiRequest(`${BASE}?start=${start}&end=${end}`)),
    onSuccess: setReport,
  });
  const restore = useMutation({
    mutationFn: async (dryRun: boolean) =>
      camelize<RestoreResult>(await apiRequest(`${BASE}/restore`, { method: "POST", body: { start, end, dry_run: dryRun } })),
  });

  async function askRestore() {
    setConfirm(await restore.mutateAsync(true));
  }
  async function doRestore() {
    const r = await restore.mutateAsync(false);
    setConfirm(null);
    pushToast(`${r.restored} entr${r.restored === 1 ? "y" : "ies"} restored from the log.`, "success");
    run.mutate();
  }

  const s = report?.summary;
  const restorable = report?.rows.filter((r) => r.restorable).length ?? 0;

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-end gap-3">
        <div className="w-40"><Input label="From" type="date" value={start} max={end} onChange={(e) => setStart(e.target.value)} /></div>
        <div className="w-40"><Input label="To" type="date" value={end} min={start} max={daysAgo(0)} onChange={(e) => setEnd(e.target.value)} /></div>
        <Button onClick={() => run.mutate()} isLoading={run.isPending}>Run audit</Button>
        {report && restorable > 0 && <Button variant="secondary" onClick={askRestore} isLoading={restore.isPending}>Restore {restorable} lost entr{restorable === 1 ? "y" : "ies"}…</Button>}
      </div>

      {s && (
        <div className="flex flex-wrap gap-x-5 gap-y-1 text-sm text-gray-700">
          <span>Logged <b>{s.logged}</b></span>
          <span>Fine <b>{s.ok}</b></span>
          <span className={s.missing ? "text-status-danger" : ""}>Missing <b>{s.missing}</b></span>
          <span className={s.hiddenNotLive ? "text-status-warning" : ""}>Store not live <b>{s.hiddenNotLive}</b></span>
          <span>Changed <b>{s.changed}</b></span>
          <span>Cleared by admin <b>{s.cleared}</b></span>
        </div>
      )}

      {report && (
        <Table>
          <thead>
            <tr><Th>Date</Th><Th>Store</Th><Th>Employee</Th><Th className="text-right">Logged</Th><Th className="text-right">Now</Th><Th>What happened</Th></tr>
          </thead>
          <tbody>
            {report.rows.length === 0 ? (
              <TableEmpty colSpan={6}>Everything employees logged in this period is in the database and visible.</TableEmpty>
            ) : (
              report.rows.map((r, i) => (
                <tr key={`${r.storeCode}-${r.orderDate}-${r.kind}-${i}`}>
                  <Td className="whitespace-nowrap">{day(r.orderDate)}</Td>
                  <Td>
                    <p className="font-medium text-gray-900">{r.storeName ?? "—"}</p>
                    <p className="text-xs text-gray-500">{r.storeCode}{r.state ? ` · ${r.state}` : ""}</p>
                  </Td>
                  <Td>{r.employee ?? "—"}</Td>
                  <Td className="text-right tabular-nums">{r.loggedCount ?? "—"}</Td>
                  <Td className="text-right tabular-nums">{r.currentCount ?? "—"}</Td>
                  <Td className="max-w-md">
                    <Badge tone={KIND[r.kind].tone}>{KIND[r.kind].label}{r.reason ? ` · ${r.reason.toLowerCase().replace("_", " ")}` : ""}</Badge>
                    <p className="mt-1 text-xs text-gray-600">{r.detail}</p>
                  </Td>
                </tr>
              ))
            )}
          </tbody>
        </Table>
      )}
      {report?.truncated && <p className="text-xs text-gray-500">Showing the first rows only; narrow the dates to see the rest.</p>}

      <Modal
        open={Boolean(confirm)}
        onClose={() => setConfirm(null)}
        title={`Restore ${confirm?.restorable ?? 0} lost entries?`}
        description="They are re-created from the audit log with the counts the employees submitted. Entries that exist, and entries an admin cleared, are never touched."
        footer={
          <>
            <Button variant="secondary" onClick={() => setConfirm(null)}>Cancel</Button>
            <Button onClick={doRestore} isLoading={restore.isPending} disabled={!confirm?.restorable}>Restore</Button>
          </>
        }
      >
        <ul className="list-disc space-y-1 pl-5 text-sm text-gray-700">
          {confirm?.examples.map((e) => <li key={e}>{e}</li>)}
          {confirm && confirm.restorable > confirm.examples.length && <li>and {confirm.restorable - confirm.examples.length} more</li>}
        </ul>
      </Modal>
    </div>
  );
}
