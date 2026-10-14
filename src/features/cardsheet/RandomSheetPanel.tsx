import { Fragment, useMemo, useState } from "react";
import { Button } from "@/components/ui/Button";
import { FileDropzone } from "@/components/ui/FileDropzone";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { Table, Td, Th } from "@/components/ui/Table";
import { ApiError, apiBlob, apiRequest } from "@/services/api";
import { useAllStores } from "@/features/stores/useAllStores";
import { isoDate } from "@/lib/dates";
import { pushToast } from "@/lib/toast";
import { MAX_DAYS, datesBetween, fmtDay, freshDistribution, type DayCount } from "./randomCounts";

interface Matched { row: number; sheet_name: string; store_id: string; store_name: string; code: string; platform: string | null; total: number; entries?: DayCount[] }
interface Suggestion { store_id: string; name: string; code: string }
interface Unmatched { row: number; name: string; total: number; reason: string; suggestions: Suggestion[] }
interface Parsed { file: string; rows: number; matched: Matched[]; unmatched: Unmatched[]; warnings: string[]; has_entries?: boolean }
interface Line { storeId: string; name: string; code: string; total: number; entries?: DayCount[] }

const SKIP = "skip";

/**
 * A sheet of outlet + total (no dates needed) becomes one PDF of cards: each outlet's total is shared out at random over
 * the dates you pick. The numbers are made on this screen, are not saved anywhere, and exist only here and in the PDF.
 */
export function RandomSheetPanel({ token, onLocked }: { token: string; onLocked: () => void }) {
  const allStores = useAllStores();
  const [file, setFile] = useState<File | null>(null);
  const [parsed, setParsed] = useState<Parsed | null>(null);
  const [choice, setChoice] = useState<Record<number, string>>({});         // unmatched row -> chosen store id or "skip"
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [allowZero, setAllowZero] = useState(true);
  const [split, setSplit] = useState<Record<string, DayCount[]> | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  const [busy, setBusy] = useState<"read" | "pdf" | null>(null);

  async function pick(f: File | undefined) {
    if (!f) return;
    setFile(f);
    setParsed(null);
    setSplit(null);
    setChoice({});
    setBusy("read");
    try {
      const form = new FormData();
      form.set("token", token);
      form.set("file", f);
      setParsed(await apiRequest<Parsed>("/developer/card-sheet/totals-preview", { method: "POST", body: form }));
    } catch (err) {
      if (err instanceof ApiError && err.status === 403) onLocked();
      setFile(null);
    } finally {
      setBusy(null);
    }
  }

  const storeById = useMemo(() => new Map((allStores.data ?? []).map((s) => [s.id, s])), [allStores.data]);
  const allOptions = useMemo(
    () => (allStores.data ?? []).map((s) => ({ value: s.id, label: `${s.externalCode} — ${s.name}` })).sort((a, b) => a.label.localeCompare(b.label)),
    [allStores.data],
  );

  // Everything that will get a card: matched stores plus unmatched rows the person pointed at a store.
  const lines = useMemo<Line[]>(() => {
    if (!parsed) return [];
    const out = new Map<string, Line>();
    for (const m of parsed.matched) out.set(m.store_id, { storeId: m.store_id, name: m.store_name, code: m.code, total: m.total, entries: m.entries });
    for (const u of parsed.unmatched) {
      const id = choice[u.row];
      if (!id || id === SKIP) continue;
      const known = storeById.get(id);
      const sug = u.suggestions.find((s) => s.store_id === id);
      const name = known?.name ?? sug?.name ?? id;
      const code = known?.externalCode ?? sug?.code ?? "";
      const prev = out.get(id);
      out.set(id, { storeId: id, name, code, total: (prev?.total ?? 0) + u.total });
    }
    return [...out.values()];
  }, [parsed, choice, storeById]);

  const unresolved = parsed ? parsed.unmatched.filter((u) => !choice[u.row]).length : 0;
  const skipped = parsed ? parsed.unmatched.filter((u) => choice[u.row] === SKIP).length : 0;
  const days = useMemo(() => (start && end && end >= start ? datesBetween(start, end) : []), [start, end]);
  // A sheet that already has daily entries is used exactly as written; nothing is randomised and no date range is needed.
  const fromSheet = !!parsed?.has_entries;
  const tooFew = !allowZero ? lines.filter((l) => l.total < days.length) : [];
  const problem =
    !parsed ? "Upload the sheet first."
    : lines.length === 0 ? "No outlet is matched to a store yet."
    : fromSheet ? null
    : !start || !end ? "Pick the start and end dates."
    : end < start ? "The end date can't be before the start date."
    : days.length > MAX_DAYS ? `The range can't be longer than ${MAX_DAYS} days.`
    : tooFew.length ? `${tooFew.length} outlet(s) have fewer bottles than days, which needs zero-count days. Turn zero days on.`
    : null;

  const sums = (id: string) => split?.[id]?.reduce((s, r) => s + r.count, 0) ?? 0;
  const allGood = !!split && lines.length > 0 && lines.every((l) => split[l.storeId] && sums(l.storeId) === l.total);

  function generate() {
    if (problem) return;
    if (fromSheet) {
      setSplit(Object.fromEntries(lines.map((l) => [l.storeId, l.entries ?? []])));
      return;
    }
    setSplit(Object.fromEntries(lines.map((l) => [l.storeId, freshDistribution(l.total, days, split?.[l.storeId], allowZero)])));
  }
  function shuffle(l: Line) {
    setSplit((s) => (s ? { ...s, [l.storeId]: freshDistribution(l.total, days, s[l.storeId], allowZero) } : s));
  }
  // Any change to the inputs makes the shown split stale, so it is cleared rather than left to be downloaded.
  const stale = <T,>(set: (v: T) => void) => (v: T) => { set(v); setSplit(null); };

  function range(kind: "this" | "last") {
    const now = new Date();
    const first = kind === "this" ? new Date(now.getFullYear(), now.getMonth(), 1) : new Date(now.getFullYear(), now.getMonth() - 1, 1);
    const last = kind === "this" ? now : new Date(now.getFullYear(), now.getMonth(), 0);
    setStart(isoDate(first));
    setEnd(isoDate(last));
    setSplit(null);
  }

  async function download() {
    if (!split || !allGood) return;
    setBusy("pdf");
    try {
      const blob = await apiBlob("/developer/card-sheet/random-bulk-pdf", {
        method: "POST",
        body: { token, items: lines.map((l) => ({ store_id: l.storeId, rows: split[l.storeId].map((r) => ({ date: r.date, count: r.count })) })) },
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `Random_Count_Cards_${start}_to_${end}.pdf`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 30_000);
      pushToast(`${lines.length} cards downloaded. Nothing was saved.`, "success");
    } catch (err) {
      if (err instanceof ApiError && err.status === 403) onLocked();
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="flex flex-col gap-5">
      <p className="rounded-xl border border-surface-border bg-surface-subtle px-4 py-3 text-sm text-gray-700">
        Upload a sheet with an outlet (name or Outlet ID) and a total on each row. A header row is not needed. Pick the dates, and each outlet's total is shared out at random across them, one standard card per outlet and month. The numbers are not saved, not added to any order or store record, and not logged.
      </p>

      <FileDropzone file={file} onPick={pick} accept=".csv,.xlsx,.xlsm" hint="CSV or Excel: outlet and total on each row" />
      {busy === "read" && <p className="text-sm text-gray-500">Reading the sheet…</p>}

      {parsed && (
        <>
          <p className="text-sm text-gray-700">
            <b>{parsed.matched.length}</b> of {parsed.matched.length + parsed.unmatched.length} outlets matched a store{parsed.unmatched.length ? `, ${parsed.unmatched.length} need your help` : ""}.
          </p>
          {parsed.warnings.map((w) => <p key={w} className="text-sm text-status-warning">{w}</p>)}

          {parsed.unmatched.length > 0 && (
            <div className="rounded-xl border border-status-warning bg-status-warning-soft px-4 py-3">
              <p className="text-sm font-semibold text-gray-800">Pick the right store for these (or skip them)</p>
              <div className="mt-3 flex flex-col gap-3">
                {parsed.unmatched.map((u) => (
                  <div key={u.row} className="grid items-end gap-3 md:grid-cols-[1fr_2fr]">
                    <div className="text-sm">
                      <p className="font-semibold text-gray-900">{u.name}</p>
                      <p className="text-xs text-gray-600">Total {u.total.toLocaleString("en-IN")} · {u.reason}</p>
                    </div>
                    <Select
                      label="Store"
                      searchable
                      placeholder="Choose a store…"
                      value={choice[u.row] ?? ""}
                      options={[
                        ...u.suggestions.map((s) => ({ value: s.store_id, label: `★ ${s.code} — ${s.name}` })),
                        { value: SKIP, label: "Skip this outlet" },
                        ...allOptions.filter((o) => !u.suggestions.some((s) => s.store_id === o.value)),
                      ]}
                      onChange={(e) => { setChoice((c) => ({ ...c, [u.row]: e.target.value })); setSplit(null); }}
                    />
                  </div>
                ))}
              </div>
              {unresolved > 0 && <p className="mt-3 text-xs text-gray-600">{unresolved} not chosen yet; they will be left out until you pick a store or skip them.</p>}
            </div>
          )}

          {fromSheet && <p className="text-sm text-gray-700">This sheet already has daily entries, so those exact numbers go on the cards. Nothing is randomised.</p>}
          {!fromSheet && <div className="grid gap-4 md:grid-cols-2">
            <Input label="Start date" type="date" value={start} onChange={(e) => stale(setStart)(e.target.value)} />
            <Input label="End date" type="date" value={end} min={start || undefined} onChange={(e) => stale(setEnd)(e.target.value)} />
          </div>}
          {!fromSheet && <div className="flex flex-wrap items-center gap-2">
            <Button size="sm" variant="secondary" onClick={() => range("this")}>This month so far</Button>
            <Button size="sm" variant="secondary" onClick={() => range("last")}>Last month</Button>
            <label className="ml-2 flex items-center gap-2 text-sm font-medium text-gray-700">
              <input type="checkbox" checked={allowZero} onChange={(e) => { setAllowZero(e.target.checked); setSplit(null); }} className="h-4 w-4 rounded border-surface-border accent-brand-500" />
              Allow zero-count days <span className="font-normal text-gray-500">(off = every day gets at least 1)</span>
            </label>
          </div>}
          {problem && (start || end || fromSheet) && <p className="text-sm text-status-warning">{problem}</p>}

          <div className="flex flex-wrap justify-end gap-2">
            <Button onClick={generate} disabled={Boolean(problem)}>{fromSheet ? "Show preview" : split ? "Shuffle all" : "Generate preview"}</Button>
            <Button onClick={download} isLoading={busy === "pdf"} disabled={!allGood}>Download {lines.length} card{lines.length === 1 ? "" : "s"} (PDF)</Button>
          </div>

          {split && (
            <>
              <p className={`text-sm font-semibold ${allGood ? "text-status-success" : "text-status-danger"}`}>
                {allGood
                  ? `Check passed: every outlet's daily counts add up to its total.${skipped ? ` ${skipped} outlet(s) skipped.` : ""}`
                  : "Some outlets don't add up to their total. Shuffle all before downloading."}
              </p>
              <Table>
                <thead><tr><Th>Outlet</Th><Th>Code</Th><Th className="text-right">Total</Th><Th className="text-right">Days</Th><Th className="text-right">Check</Th><Th className="text-right"> </Th></tr></thead>
                <tbody>
                  {lines.map((l) => (
                    <Fragment key={l.storeId}>
                      <tr>
                        <Td className="font-medium text-gray-900">{l.name}</Td>
                        <Td className="font-mono text-xs">{l.code}</Td>
                        <Td className="text-right tabular-nums">{l.total.toLocaleString("en-IN")}</Td>
                        <Td className="text-right tabular-nums">{split[l.storeId]?.length ?? days.length}</Td>
                        <Td className={`text-right font-bold ${sums(l.storeId) === l.total ? "text-status-success" : "text-status-danger"}`}>{sums(l.storeId) === l.total ? "✓" : "✗"}</Td>
                        <Td className="whitespace-nowrap text-right">
                          {!fromSheet && <Button size="sm" variant="ghost" onClick={() => shuffle(l)}>Shuffle</Button>}
                          <Button size="sm" variant="ghost" onClick={() => setOpen(open === l.storeId ? null : l.storeId)}>{open === l.storeId ? "Hide" : "Days"}</Button>
                        </Td>
                      </tr>
                      {open === l.storeId && (
                        <tr>
                          <Td colSpan={6} className="bg-surface-subtle">
                            <div className="flex flex-wrap gap-2 py-1">
                              {split[l.storeId].map((r) => (
                                <span key={r.date} className="rounded-md bg-surface px-2 py-1 text-xs ring-1 ring-surface-border"><span className="text-gray-500">{fmtDay(r.date)}</span> <b className="tabular-nums">{r.count}</b></span>
                              ))}
                            </div>
                          </Td>
                        </tr>
                      )}
                    </Fragment>
                  ))}
                </tbody>
              </Table>
            </>
          )}
        </>
      )}
    </div>
  );
}
