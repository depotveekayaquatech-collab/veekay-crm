import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Modal } from "@/components/ui/Modal";
import { Table, Td, Th } from "@/components/ui/Table";
import { camelize } from "@/lib/camel";
import { daysAgo } from "@/lib/dates";
import { pushToast } from "@/lib/toast";
import { apiRequest } from "@/services/api";

type Kind = "OK" | "MISSING" | "CLEARED" | "CHANGED" | "HIDDEN_NOT_LIVE";

interface AuditRow {
  kind: Kind;
  reason?: string;
  orderDate: string;
  storeCode: string | null;
  storeName: string | null;
  state: string | null;
  employee: string | null;
  employeeCode: string | null;
  loggedCount: number | null;
  currentCount: number | null;
  restorable: boolean;
  detail: string;
}

interface AuditReport {
  start: string;
  end: string;
  summary: { logged: number; ok: number; missing: number; cleared: number; changed: number; hiddenNotLive: number };
  days: { date: string; stored: number; logged: number; fromOtherSources: number }[];
  people: { name: string | null; code: string | null; entries: number; days: Record<string, number> }[];
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
const KIND: Record<Kind, { label: string; tone: "danger" | "warning" | "info" | "neutral" | "success" }> = {
  OK: { label: "Saved", tone: "success" },
  MISSING: { label: "Missing", tone: "danger" },
  HIDDEN_NOT_LIVE: { label: "Store not live", tone: "warning" },
  CHANGED: { label: "Changed", tone: "info" },
  CLEARED: { label: "Cleared by admin", tone: "neutral" },
};
const day = (iso: string) => new Date(`${iso}T00:00:00`).toLocaleDateString("en-IN", { weekday: "short", day: "2-digit", month: "short" });
const n = (v: number) => v.toLocaleString("en-IN");

/** Developer: what employees submitted (the audit log) against what is stored and visible, per day and per employee, why any entry is missing or hidden, and the repair. */
export function EntryAudit() {
  const [start, setStart] = useState(daysAgo(3));
  const [end, setEnd] = useState(daysAgo(0));
  const [who, setWho] = useState("");
  const [every, setEvery] = useState(false);
  const [report, setReport] = useState<AuditReport | null>(null);
  const [confirm, setConfirm] = useState<RestoreResult | null>(null);

  const run = useMutation({
    mutationFn: async () => {
      const q = new URLSearchParams({ start, end });
      if (who.trim()) q.set("employee", who.trim());
      if (every) q.set("show_all", "true");
      return camelize<AuditReport>(await apiRequest(`${BASE}?${q}`));
    },
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
  const problems = s ? s.missing + s.changed + s.hiddenNotLive : 0;
  const restorable = report?.rows.filter((r) => r.restorable).length ?? 0;
  const dayCols = report?.days ?? [];

  return (
    <div className="flex flex-col gap-4">
      <form
        className="flex flex-wrap items-end gap-3"
        onSubmit={(e) => { e.preventDefault(); run.mutate(); }}
      >
        <div className="w-40"><Input label="From" type="date" value={start} max={end} onChange={(e) => setStart(e.target.value)} /></div>
        <div className="w-40"><Input label="To" type="date" value={end} min={start} max={daysAgo(0)} onChange={(e) => setEnd(e.target.value)} /></div>
        <div className="w-56"><Input label="Employee (name or ID, optional)" value={who} onChange={(e) => setWho(e.target.value)} placeholder="e.g. Ravi or EMP001" /></div>
        <label className="flex h-10 items-center gap-2 text-sm text-gray-700">
          <input type="checkbox" className="h-4 w-4" checked={every} onChange={(e) => setEvery(e.target.checked)} />
          List every entry, not only problems
        </label>
        <Button type="submit" isLoading={run.isPending}>Run audit</Button>
        {report && restorable > 0 && (
          <Button type="button" variant="secondary" onClick={askRestore} isLoading={restore.isPending}>Restore {restorable} lost entr{restorable === 1 ? "y" : "ies"}…</Button>
        )}
      </form>

      {report && s && (
        <>
          {problems === 0 ? (
            <div role="status" className="rounded-xl border border-status-success/30 bg-status-success/10 px-4 py-3 text-sm text-gray-800">
              <b>Nothing is wrong.</b> All {n(s.logged)} entries employees marked in the app between {day(report.start)} and {day(report.end)} are saved, unchanged,
              and their stores are live. {s.cleared ? `${n(s.cleared)} were cleared on purpose by an admin. ` : ""}
              If an employee says an entry is missing, it was probably never sent from their phone, or it is under another store or day: look it up below with their name.
            </div>
          ) : (
            <div role="alert" className="rounded-xl border border-status-warning/40 bg-status-warning/10 px-4 py-3 text-sm text-gray-800">
              <b>{n(problems)} entr{problems === 1 ? "y needs" : "ies need"} a look.</b>{" "}
              {s.missing ? `${n(s.missing)} missing. ` : ""}{s.hiddenNotLive ? `${n(s.hiddenNotLive)} saved but hidden because the store is no longer live. ` : ""}{s.changed ? `${n(s.changed)} changed since the employee entered them.` : ""}
            </div>
          )}

          <div className="flex flex-wrap gap-x-5 gap-y-1 text-sm text-gray-700">
            <span>Marked in the app <b>{n(s.logged)}</b></span>
            <span>Saved and fine <b>{n(s.ok)}</b></span>
            <span className={s.missing ? "text-status-danger" : ""}>Missing <b>{n(s.missing)}</b></span>
            <span className={s.hiddenNotLive ? "text-status-warning" : ""}>Store not live <b>{n(s.hiddenNotLive)}</b></span>
            <span>Changed <b>{n(s.changed)}</b></span>
            <span>Cleared by admin <b>{n(s.cleared)}</b></span>
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            <div>
              <h4 className="mb-2 text-sm font-bold text-gray-900">By day</h4>
              <Table>
                <thead>
                  <tr><Th>Day</Th><Th className="text-right">In the database</Th><Th className="text-right">Marked in the app</Th><Th className="text-right">From other sources</Th></tr>
                </thead>
                <tbody>
                  {dayCols.map((d) => (
                    <tr key={d.date}>
                      <Td className="whitespace-nowrap">{day(d.date)}</Td>
                      <Td className="text-right tabular-nums">{n(d.stored)}</Td>
                      <Td className="text-right tabular-nums">{n(d.logged)}</Td>
                      <Td className="text-right tabular-nums text-gray-600">{n(d.fromOtherSources)}</Td>
                    </tr>
                  ))}
                </tbody>
              </Table>
              <p className="mt-1 text-xs text-gray-500">"From other sources" is stored entries nobody marked in the app: the order sheet import, an admin's entry, or a restore.</p>
            </div>
            <div>
              <h4 className="mb-2 text-sm font-bold text-gray-900">By employee{who.trim() ? ` matching "${who.trim()}"` : ""}</h4>
              <Table>
                <thead>
                  <tr><Th>Employee</Th><Th className="text-right">Entries</Th><Th>Per day</Th></tr>
                </thead>
                <tbody>
                  {report.people.length === 0 ? (
                    <tr><Td colSpan={3} className="text-sm text-gray-500">Nobody marked an entry in the app in this period.</Td></tr>
                  ) : (
                    report.people.map((p) => (
                      <tr key={p.code ?? p.name}>
                        <Td><span className="font-medium text-gray-900">{p.name ?? "—"}</span> <span className="text-xs text-gray-500">{p.code}</span></Td>
                        <Td className="text-right tabular-nums">{n(p.entries)}</Td>
                        <Td className="text-xs text-gray-600">{dayCols.filter((d) => p.days[d.date]).map((d) => `${day(d.date)}: ${p.days[d.date]}`).join(" · ")}</Td>
                      </tr>
                    ))
                  )}
                </tbody>
              </Table>
            </div>
          </div>

          {report.rows.length > 0 && (
            <div>
              <h4 className="mb-2 text-sm font-bold text-gray-900">{every ? "Every entry" : "Entries that need a look"}</h4>
              <Table>
                <thead>
                  <tr><Th>Date</Th><Th>Store</Th><Th>Employee</Th><Th className="text-right">Entered</Th><Th className="text-right">Now</Th><Th>What happened</Th></tr>
                </thead>
                <tbody>
                  {report.rows.map((r, i) => (
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
                        {r.kind !== "OK" && <p className="mt-1 text-xs text-gray-600">{r.detail}</p>}
                      </Td>
                    </tr>
                  ))}
                </tbody>
              </Table>
              {report.truncated && <p className="mt-1 text-xs text-gray-500">Showing the first rows only; narrow the dates or pick an employee to see the rest.</p>}
            </div>
          )}
        </>
      )}

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
