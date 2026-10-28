import { useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/Button";
import { IconUpload } from "@/components/ui/icons";
import { dateLabel, istToday } from "@/features/capping/helpers";
import { field } from "@/features/capping/styles";
import { pushToast } from "@/lib/toast";
import { importDatedSheet, type DatedImportResult } from "@/services/capping";

const n = (v: number) => v.toLocaleString("en-IN");

/** What the sheet says, in plain words: how many stores, how many start on day 1 and which start later. */
function Preview({ r }: { r: DatedImportResult }) {
  const later = r.starts.filter((s) => s.date.slice(8) !== "01");
  return (
    <div className="mt-4 flex flex-col gap-3">
      <p className="text-xs text-gray-500">Read as: {r.readAs}.</p>
      <div className="grid gap-3 sm:grid-cols-4">
        {[
          ["Stores found", n(r.stores)],
          ["Start on day 1", n(r.dayOne)],
          ["Start later in the month", n(r.midMonth)],
          ["Not in the CRM", n(r.unknownStores)],
        ].map(([label, value]) => (
          <div key={label} className="rounded-lg border border-surface-border bg-surface-subtle/60 px-3 py-2">
            <div className="text-[11px] font-bold uppercase tracking-wide text-gray-500">{label}</div>
            <div className="text-xl font-extrabold tabular-nums text-heading">{value}</div>
          </div>
        ))}
      </div>
      <p className="text-sm text-gray-700">
        {r.dryRun ? "Applying will add" : "Added"} <b>{n(r.newRows)}</b> capping change{r.newRows === 1 ? "" : "s"}
        {r.updatedRows > 0 && <>, change <b>{n(r.updatedRows)}</b></>}
        {r.removedRows > 0 && <>, remove <b>{n(r.removedRows)}</b> that the sheet does not have</>}
        {r.zeroDays > 0 && <>, and mark <b>{n(r.zeroDays)}</b> zero-capping day{r.zeroDays === 1 ? "" : "s"}</>}. {r.unchangedStores > 0 && <>{n(r.unchangedStores)} store{r.unchangedStores === 1 ? " is" : "s are"} already up to date.</>}
      </p>
      {later.length > 0 && (
        <div>
          <div className="text-xs font-bold uppercase tracking-wide text-gray-500">Stores that start part-way through</div>
          <ul className="mt-1.5 flex flex-wrap gap-2">
            {later.map((s) => (
              <li key={s.date} className="rounded-full bg-status-warning-soft px-3 py-1 text-sm ring-1 ring-status-warning/25">
                <span className="font-semibold tabular-nums">{dateLabel(s.date)}</span> <span className="text-gray-600">· {n(s.stores)} store{s.stores === 1 ? "" : "s"}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
      {r.conflicts > 0 && !r.replace && (
        <p className="rounded-lg bg-status-warning-soft px-3 py-2 text-sm text-gray-800">
          {n(r.conflicts)} date{r.conflicts === 1 ? "" : "s"} already ha{r.conflicts === 1 ? "s" : "ve"} a different capping in the CRM and will be left alone. Tick “Replace” to use the sheet instead.
        </p>
      )}
      {r.warnings.length > 0 && (
        <ul className="list-disc pl-5 text-xs text-gray-600">{r.warnings.map((w) => <li key={w}>{w}</li>)}</ul>
      )}
      {r.sample.length > 0 && (
        <div className="overflow-x-auto rounded-xl border border-surface-border">
          <table className="w-full min-w-[560px] border-collapse text-sm">
            <thead>
              <tr className="bg-surface-subtle/80 text-left text-[11px] font-bold uppercase tracking-wider text-gray-500">
                <th className="px-3 py-2">Store</th><th className="px-3 py-2">Starts</th><th className="px-3 py-2">Current capping</th><th className="px-3 py-2">Changes in the sheet</th>
              </tr>
            </thead>
            <tbody>
              {r.sample.map((s) => (
                <tr key={s.outletId} className="border-t border-surface-border/60">
                  <td className="px-3 py-2"><div className="font-semibold text-gray-900">{s.store}</div><div className="text-xs text-gray-500">{s.outletId}</div></td>
                  <td className="px-3 py-2 tabular-nums">{s.start ? dateLabel(s.start) : "—"}</td>
                  <td className="px-3 py-2 font-bold tabular-nums">{s.current ?? "—"}</td>
                  <td className="px-3 py-2 text-gray-700">
                    {s.changes.map((c) => `${c.capping} from ${dateLabel(c.date).slice(0, 6)}`).join(", ")}
                    {s.differsFromCrm.length > 0 && <span className="ml-2 text-xs text-status-warning">CRM has {s.differsFromCrm.map((d) => `${d.crm} on ${dateLabel(d.date).slice(0, 6)}`).join(", ")}</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {r.stores > r.sample.length && <p className="border-t border-surface-border/60 px-3 py-2 text-xs text-gray-500">Showing {r.sample.length} of {n(r.stores)} stores.</p>}
        </div>
      )}
    </div>
  );
}

/**
 * Upload the capping sheet you already keep (store names with the capping on each date, or one capping per store with an Effective from column).
 * It is read first and nothing is saved until you apply it: the page shows how many stores start on day 1 and which start part-way through.
 */
export function CappingSheetUpload() {
  const qc = useQueryClient();
  const today = istToday();
  const input = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [replace, setReplace] = useState(false);
  const [startDate, setStartDate] = useState(`${today.slice(0, 7)}-01`);
  const [result, setResult] = useState<DatedImportResult | null>(null);

  const run = useMutation({
    mutationFn: (dryRun: boolean) => importDatedSheet(file as File, { dryRun, replace, startDate }),
    onSuccess: (r) => {
      setResult(r);
      if (r.applied) {
        pushToast(`Capping loaded for ${n(r.stores)} stores: ${n(r.dayOne)} start on day 1, ${n(r.midMonth)} later.`, "success");
        void qc.invalidateQueries({ queryKey: ["capping"] });
      }
    },
  });

  const pick = (f: File | null) => {
    setFile(f);
    setResult(null);
  };

  return (
    <section className="rounded-xl border border-surface-border bg-surface p-4 shadow-card" aria-label="Upload a capping sheet">
      <h3 className="text-sm font-bold text-gray-900">Upload a capping sheet</h3>
      <p className="mt-1 text-xs text-gray-500">
        Use the sheet you already have: a store column with either one column per date (the capping on each day) or a single Capping column
        (optionally with Effective from). It works out which date each store's capping starts on and the capping as of today. Nothing is saved until you press Apply.
      </p>
      <div className="mt-3 grid gap-3 md:grid-cols-[minmax(0,2fr)_minmax(0,1fr)_auto] md:items-end">
        <div className="flex flex-col gap-1.5 text-[13px] font-semibold text-gray-700">
          Sheet (.xlsx or .csv)
          <div className="flex items-center gap-2">
            <input ref={input} type="file" accept=".csv,.xlsx,.xlsm" className="sr-only" aria-label="Capping sheet" onChange={(e) => pick(e.target.files?.[0] ?? null)} />
            <Button variant="secondary" onClick={() => input.current?.click()}><IconUpload className="h-4 w-4" /> Choose file</Button>
            <span className="truncate text-sm font-normal text-gray-600">{file ? file.name : "No file chosen"}</span>
          </div>
        </div>
        <label className="flex flex-col gap-1.5 text-[13px] font-semibold text-gray-700">
          Start date for stores with no date in the sheet
          <input className={field} type="date" value={startDate} min="2024-01-01" max={today} onChange={(e) => { setStartDate(e.target.value); setResult(null); }} />
        </label>
        <Button onClick={() => run.mutate(true)} isLoading={run.isPending && run.variables === true} disabled={!file || !startDate}>Check sheet</Button>
      </div>
      <label className="mt-3 flex items-start gap-2 text-sm text-gray-700">
        <input type="checkbox" className="mt-1" checked={replace} onChange={(e) => { setReplace(e.target.checked); setResult(null); }} />
        <span>Replace what the CRM has from each store's first date in the sheet <span className="text-xs text-gray-500">(otherwise dates that already have a different capping are left alone)</span></span>
      </label>

      {result && <Preview r={result} />}

      {result && result.dryRun && result.stores > 0 && (
        <div className="mt-4">
          <Button onClick={() => run.mutate(false)} isLoading={run.isPending && run.variables === false}>Apply to {n(result.stores)} stores</Button>
        </div>
      )}
    </section>
  );
}
