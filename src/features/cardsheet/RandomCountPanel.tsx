import { useMemo, useState } from "react";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { Table, Td, Th } from "@/components/ui/Table";
import { ApiError, apiBlob } from "@/services/api";
import { useAllStores } from "@/features/stores/useAllStores";
import { usePartners } from "@/features/stores/useStores";
import { pushToast } from "@/lib/toast";
import { MAX_DAYS, MAX_TOTAL, datesBetween, fmtDay, freshDistribution, type DayCount } from "./randomCounts";

/**
 * Temporary random split of a bottle total over a date range, printed on the standard store card.
 * The split lives only in this component's state. The one request made (the PDF) renders and returns the card; nothing is stored.
 */
export function RandomCountPanel({ token, onLocked }: { token: string; onLocked: () => void }) {
  const [totalText, setTotalText] = useState("");
  const [partner, setPartner] = useState("");
  const [storeId, setStoreId] = useState("");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [rows, setRows] = useState<DayCount[] | null>(null);
  const [allowZero, setAllowZero] = useState(true);
  const [busy, setBusy] = useState(false);

  const allStores = useAllStores();
  const { data: partners = [] } = usePartners();
  const choices = useMemo(
    () => (allStores.data ?? []).filter((x) => !partner || x.partnerSlug === partner).sort((x, y) => x.name.localeCompare(y.name)),
    [allStores.data, partner],
  );
  const store = useMemo(() => (allStores.data ?? []).find((x) => x.id === storeId) ?? null, [allStores.data, storeId]);

  const total = /^\d+$/.test(totalText) ? Number(totalText) : null;
  const days = useMemo(() => (start && end && end >= start ? datesBetween(start, end) : []), [start, end]);
  const problem =
    totalText === "" ? "Enter the total count."
    : total === null ? "Total must be a whole number, zero or more."
    : total > MAX_TOTAL ? `Total can't be more than ${MAX_TOTAL.toLocaleString("en-IN")}.`
    : !store ? "Search for and select a store."
    : !start || !end ? "Pick the start and end dates."
    : end < start ? "The end date can't be before the start date."
    : days.length > MAX_DAYS ? `The range can't be longer than ${MAX_DAYS} days.`
    : !allowZero && total < days.length ? `${days.length} days need at least ${days.length} bottles when zero days are off. Turn zero days on or raise the total.`
    : null;

  // Any change to the inputs makes the shown split stale, so it is cleared rather than left to be downloaded.
  function changed(set: (v: string) => void, value: string) {
    set(value);
    setRows(null);
  }

  function generate() {
    if (problem || total === null) return;
    setRows((prev) => freshDistribution(total, days, prev ?? undefined, allowZero));
  }

  async function download() {
    if (!rows || !store) return;
    setBusy(true);
    try {
      const blob = await apiBlob("/developer/card-sheet/random-pdf", {
        method: "POST",
        body: { token, store_id: store.id, rows: rows.map((r) => ({ date: r.date, count: r.count })) },
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${store.externalCode.replace(/[^\w-]+/g, "_")}_Random_Count_Card_${rows[0].date}_to_${rows[rows.length - 1].date}.pdf`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 30_000);
      pushToast("Card downloaded. Nothing was saved.", "success");
    } catch (err) {
      if (err instanceof ApiError && err.status === 403) onLocked();
    } finally {
      setBusy(false);
    }
  }

  const sum = rows?.reduce((s, r) => s + r.count, 0) ?? 0;

  return (
    <div className="flex flex-col gap-5">
      <p className="rounded-xl border border-surface-border bg-surface-subtle px-4 py-3 text-sm text-gray-700">
        Shares a total at random across the days you pick and prints it on the standard store card (one card per month). The numbers are temporary: they are not saved, not added to any order or store record, and not logged. They exist only on this screen and in the PDF you download.
      </p>

      <div className="grid gap-4 md:grid-cols-2">
        <Input label="Total count" inputMode="numeric" autoComplete="off" placeholder="e.g. 100" value={totalText} onChange={(e) => changed(setTotalText, e.target.value.trim())} />
        <Select
          label="Partner"
          placeholder="All partners"
          value={partner}
          options={partners.map((p) => ({ value: p.slug, label: p.name }))}
          onChange={(e) => { setPartner(e.target.value); setStoreId(""); setRows(null); }}
        />
        <Select
          label="Store"
          searchable
          placeholder={allStores.isLoading ? "Loading stores…" : `Search ${choices.length} stores by Outlet ID or name`}
          value={storeId}
          options={choices.map((x) => ({ value: x.id, label: `${x.externalCode} — ${x.name}` }))}
          onChange={(e) => { setStoreId(e.target.value); setRows(null); }}
        />
        <Input label="Start date" type="date" value={start} onChange={(e) => changed(setStart, e.target.value)} />
        <Input label="End date" type="date" value={end} min={start || undefined} onChange={(e) => changed(setEnd, e.target.value)} />
      </div>

      <label className="flex items-center gap-2 text-sm font-medium text-gray-700">
        <input type="checkbox" checked={allowZero} onChange={(e) => { setAllowZero(e.target.checked); setRows(null); }} className="h-4 w-4 rounded border-surface-border accent-brand-500" />
        Allow zero-count days <span className="font-normal text-gray-500">(off = every day gets at least 1)</span>
      </label>
      {allStores.isError && <p className="text-sm text-status-danger">The store list could not be loaded. Reload the page and try again.</p>}
      {allStores.data && choices.length === 0 && <p className="text-sm text-status-warning">No stores found for that partner.</p>}
      {store && (
        <p className="text-sm text-gray-700">
          Selected: <b className="font-mono">{store.externalCode}</b> — <b>{store.name}</b>
        </p>
      )}
      {problem && (totalText !== "" || storeId || start || end) && <p className="text-sm text-status-warning">{problem}</p>}

      <div className="flex flex-wrap justify-end gap-2">
        <Button onClick={generate} disabled={Boolean(problem)}>Generate preview</Button>
        <Button variant="secondary" onClick={generate} disabled={Boolean(problem) || !rows}>Regenerate</Button>
        <Button onClick={download} isLoading={busy} disabled={!rows || sum !== total}>Download PDF</Button>
      </div>

      {rows && store && (
        <>
          <dl className="grid gap-3 rounded-xl border border-surface-border bg-surface px-4 py-3 text-sm shadow-card sm:grid-cols-2 lg:grid-cols-3">
            {[
              ["Outlet ID", store.externalCode], ["Outlet name", store.name],
              ["Start date", fmtDay(rows[0].date)], ["End date", fmtDay(rows[rows.length - 1].date)],
              ["Total entered", (total ?? 0).toLocaleString("en-IN")], ["Dates in range", String(rows.length)],
            ].map(([k, v]) => (
              <div key={k}><dt className="text-[11px] font-bold uppercase tracking-wider text-gray-500">{k}</dt><dd className="mt-0.5 break-words font-semibold text-heading">{v}</dd></div>
            ))}
          </dl>
          {sum === total
            ? <p className="text-sm font-semibold text-status-success">Check passed: the {rows.length} daily counts add up to {sum.toLocaleString("en-IN")}, the total you entered.</p>
            : <p className="text-sm font-semibold text-status-danger">The daily counts add up to {sum.toLocaleString("en-IN")}, not {(total ?? 0).toLocaleString("en-IN")}. Regenerate before downloading.</p>}
          <Table>
            <thead><tr><Th>Date</Th><Th className="text-right">Bottle count</Th></tr></thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.date}><Td>{fmtDay(r.date)}</Td><Td className="text-right tabular-nums">{r.count}</Td></tr>
              ))}
              <tr className="bg-surface-subtle">
                <Td className="font-bold text-heading">Total</Td>
                <Td className="text-right text-base font-bold tabular-nums text-heading">{sum.toLocaleString("en-IN")}</Td>
              </tr>
            </tbody>
          </Table>
        </>
      )}
    </div>
  );
}
