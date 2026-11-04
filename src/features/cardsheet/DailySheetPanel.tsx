import { Fragment, useMemo, useRef, useState } from "react";
import { Button } from "@/components/ui/Button";
import { FileDropzone } from "@/components/ui/FileDropzone";
import { Input } from "@/components/ui/Input";
import { Table, Td, Th } from "@/components/ui/Table";
import { TemplateLink } from "@/components/ui/TemplateLink";
import { ApiError, apiBlob, apiRequest } from "@/services/api";
import { useAllStores } from "@/features/stores/useAllStores";
import { isoDate } from "@/lib/dates";
import { pushToast } from "@/lib/toast";
import { buildLines, lineProblems, lineTotal, type DailyParsed } from "./dailySheet";
import { fmtDay } from "./randomCounts";
import { SKIP } from "./sheetPicker";
import { UnmatchedPicker } from "./UnmatchedPicker";

/**
 * A sheet of store name, total count and one column per day of a chosen month. The numbers in the sheet are the entries and are
 * printed on the standard store card exactly as written (nothing is randomised). Nothing is saved: the sheet is read, shown here,
 * and drawn into the PDF you download.
 */
export function DailySheetPanel({ token, onLocked }: { token: string; onLocked: () => void }) {
  const allStores = useAllStores();
  const [month, setMonth] = useState(() => isoDate(new Date()).slice(0, 7));
  const [file, setFile] = useState<File | null>(null);
  const [parsed, setParsed] = useState<DailyParsed | null>(null);
  const [choice, setChoice] = useState<Record<number, string>>({});         // unmatched row -> chosen store id or "skip"
  const [open, setOpen] = useState<string | null>(null);
  const [busy, setBusy] = useState<"read" | "pdf" | null>(null);
  const latestRead = useRef(0);                                              // a slow answer for an old month must not replace a newer one

  async function read(f: File, forMonth: string) {
    const mine = ++latestRead.current;
    setParsed(null);
    setChoice({});
    setOpen(null);
    setBusy("read");
    try {
      const form = new FormData();
      form.set("token", token);
      form.set("month", forMonth);
      form.set("file", f);
      const result = await apiRequest<DailyParsed>("/developer/card-sheet/daily-preview", { method: "POST", body: form });
      if (mine === latestRead.current) setParsed(result);
    } catch (err) {
      if (err instanceof ApiError && err.status === 403) onLocked();
      if (mine === latestRead.current) setFile(null);
    } finally {
      if (mine === latestRead.current) setBusy(null);
    }
  }

  function changeMonth(value: string) {
    if (!value) return;
    setMonth(value);
    if (file) void read(file, value);
  }

  const storeById = useMemo(() => new Map((allStores.data ?? []).map((s) => [s.id, s])), [allStores.data]);
  const allOptions = useMemo(
    () => (allStores.data ?? []).map((s) => ({ value: s.id, label: `${s.externalCode} — ${s.name}` })).sort((a, b) => a.label.localeCompare(b.label)),
    [allStores.data],
  );
  const lines = useMemo(
    () => (parsed ? buildLines(parsed, choice, (id) => { const s = storeById.get(id); return s && { name: s.name, code: s.externalCode }; }) : []),
    [parsed, choice, storeById],
  );
  const ready = lines.filter((l) => lineProblems(l).length === 0);
  const skipped = parsed ? parsed.unmatched.filter((u) => choice[u.row] === SKIP).length : 0;

  async function download() {
    if (!ready.length) return;
    setBusy("pdf");
    try {
      const blob = await apiBlob("/developer/card-sheet/random-bulk-pdf", {
        method: "POST",
        body: { token, items: ready.map((l) => ({ store_id: l.storeId, rows: l.entries.map((e) => ({ date: e.date, count: e.count })) })) },
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `Daily_Entry_Cards_${month}.pdf`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 30_000);
      pushToast(`${ready.length} card${ready.length === 1 ? "" : "s"} downloaded. Nothing was saved.`, "success");
    } catch (err) {
      if (err instanceof ApiError && err.status === 403) onLocked();
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="flex flex-col gap-5">
      <p className="rounded-xl border border-surface-border bg-surface-subtle px-4 py-3 text-sm text-gray-700">
        Upload a sheet with the store name, the total count, and one column for each day of the month (1, 2, 3 …). The numbers you write under each day are printed on the standard store card exactly as they are; nothing is randomised.
        Leave a day empty for no entry; type 0 for a zero entry. The total count is checked against the days. Nothing is saved, added to any order or store, or logged.
      </p>

      <div className="grid gap-4 md:grid-cols-2">
        <Input label="Month the sheet is for" type="month" value={month} onChange={(e) => changeMonth(e.target.value)} />
      </div>
      <FileDropzone file={file} onPick={(f) => { if (f) { setFile(f); void read(f, month); } }} accept=".csv,.xlsx,.xlsm" hint="CSV or Excel: store name, total count, then a column for each day" />
      <TemplateLink kind="cardsheet-daily" month={month} label="Download a sample sheet for this month" className="-mt-3 self-start" />
      {busy === "read" && <p className="text-sm text-gray-500">Reading the sheet…</p>}

      {parsed && (
        <>
          <p className="text-sm text-gray-700">
            <b>{parsed.matched.length}</b> of {parsed.matched.length + parsed.unmatched.length} outlets matched a store{parsed.unmatched.length ? `, ${parsed.unmatched.length} need your help` : ""}.
          </p>
          {parsed.warnings.map((w) => <p key={w} className="text-sm text-status-warning">{w}</p>)}
          {parsed.unmatched.length > 0 && (
            <UnmatchedPicker rows={parsed.unmatched} choice={choice} allOptions={allOptions} onChoose={(row, value) => setChoice((c) => ({ ...c, [row]: value }))} />
          )}

          <div className="flex flex-wrap items-center justify-between gap-3">
            <p className={`text-sm font-semibold ${ready.length === lines.length && lines.length > 0 ? "text-status-success" : "text-status-warning"}`}>
              {lines.length === 0
                ? "No outlet is matched to a store yet."
                : `${ready.length} of ${lines.length} outlets are ready to print${ready.length < lines.length ? `; ${lines.length - ready.length} left out until the sheet is fixed` : ""}.${skipped ? ` ${skipped} skipped.` : ""}`}
            </p>
            <Button onClick={download} isLoading={busy === "pdf"} disabled={ready.length === 0}>
              Download {ready.length} card{ready.length === 1 ? "" : "s"} (PDF)
            </Button>
          </div>

          {lines.length > 0 && (
            <Table>
              <thead>
                <tr><Th>Outlet</Th><Th>Code</Th><Th className="text-right">Sheet total</Th><Th className="text-right">Days add up to</Th><Th className="text-right">Days filled</Th><Th className="text-right">Check</Th><Th className="text-right"> </Th></tr>
              </thead>
              <tbody>
                {lines.map((l) => {
                  const problems = lineProblems(l);
                  return (
                    <Fragment key={l.storeId}>
                      <tr>
                        <Td className="font-medium text-gray-900">
                          {l.name}
                          {problems.map((p) => <span key={p} className="mt-0.5 block text-xs font-normal text-status-danger">{p}</span>)}
                        </Td>
                        <Td className="font-mono text-xs">{l.code}</Td>
                        <Td className="text-right tabular-nums">{l.sheetTotal === null ? "—" : l.sheetTotal.toLocaleString("en-IN")}</Td>
                        <Td className="text-right tabular-nums">{lineTotal(l).toLocaleString("en-IN")}</Td>
                        <Td className="text-right tabular-nums">{l.entries.length}</Td>
                        <Td className={`text-right font-bold ${problems.length ? "text-status-danger" : "text-status-success"}`}>{problems.length ? "✗" : "✓"}</Td>
                        <Td className="whitespace-nowrap text-right">
                          <Button size="sm" variant="ghost" onClick={() => setOpen(open === l.storeId ? null : l.storeId)}>{open === l.storeId ? "Hide" : "Days"}</Button>
                        </Td>
                      </tr>
                      {open === l.storeId && (
                        <tr>
                          <Td colSpan={7} className="bg-surface-subtle">
                            <div className="flex flex-wrap gap-2 py-1">
                              {l.entries.map((e) => (
                                <span key={e.date} className="rounded-md bg-surface px-2 py-1 text-xs ring-1 ring-surface-border"><span className="text-gray-500">{fmtDay(e.date)}</span> <b className="tabular-nums">{e.count}</b></span>
                              ))}
                              {l.entries.length === 0 && <span className="text-xs text-gray-500">No daily numbers.</span>}
                            </div>
                          </Td>
                        </tr>
                      )}
                    </Fragment>
                  );
                })}
              </tbody>
            </Table>
          )}
        </>
      )}
    </div>
  );
}
