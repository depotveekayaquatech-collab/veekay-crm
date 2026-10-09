import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Table, TableEmpty, Td, Th } from "@/components/ui/Table";
import { LABELS_PER_PDF, csvPath, downloadFile, labelsPath, useBatches, useGenerate, when, type Batch } from "@/features/bottles/api";

function BatchRow({ b }: { b: Batch }) {
  const [busy, setBusy] = useState(false);
  const parts = Math.ceil(b.quantity / LABELS_PER_PDF);
  async function run(fn: () => Promise<void>) {
    setBusy(true);
    try {
      await fn();
    } catch {
      /* the API layer already showed the reason */
    } finally {
      setBusy(false);
    }
  }
  return (
    <tr>
      <Td className="whitespace-nowrap">{when(b.createdAt)}</Td>
      <Td className="tabular-nums">{b.quantity.toLocaleString("en-IN")}</Td>
      <Td className="font-mono text-xs">{b.firstSerial}<br />{b.lastSerial}</Td>
      <Td>{b.note ?? "—"}<p className="text-xs text-gray-500">{b.createdByName}</p></Td>
      <Td>
        <div className="flex flex-wrap gap-1.5">
          {Array.from({ length: Math.min(parts, 60) }, (_, i) => (
            <Button key={i} size="sm" variant="secondary" disabled={busy} onClick={() => run(() => downloadFile(labelsPath(b.id, i * LABELS_PER_PDF + 1), `labels-${i + 1}.pdf`))}>
              {parts > 1 ? `PDF ${i * LABELS_PER_PDF + 1}–${Math.min((i + 1) * LABELS_PER_PDF, b.quantity)}` : "Labels PDF"}
            </Button>
          ))}
          {parts > 60 && <span className="text-xs text-gray-500">Use the CSV for the rest.</span>}
          <Button size="sm" variant="ghost" disabled={busy} onClick={() => run(() => downloadFile(csvPath(b.id), "bottle-serials.csv"))}>CSV</Button>
        </div>
      </Td>
    </tr>
  );
}

export function PrintCodes() {
  const [qty, setQty] = useState("");
  const [note, setNote] = useState("");
  const gen = useGenerate();
  const { data: batches } = useBatches(true);
  const n = Number(qty.replace(/,/g, ""));
  const valid = Number.isInteger(n) && n >= 1 && n <= 200000;

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-end gap-3 rounded-xl border border-surface-border bg-surface p-4 shadow-card">
        <div className="w-full sm:w-64"><Input label="How many codes? (up to 2,00,000)" inputMode="numeric" value={qty} onChange={(e) => setQty(e.target.value)} /></div>
        <div className="w-full flex-1 sm:min-w-[200px]"><Input label="Note (optional)" value={note} onChange={(e) => setNote(e.target.value)} placeholder="e.g. 20L jars, Sept order" /></div>
        <Button isLoading={gen.isPending} disabled={!valid} onClick={() => gen.mutate({ quantity: n, note }, { onSuccess: () => { setQty(""); setNote(""); } })}>Generate codes</Button>
      </div>
      <p className="text-sm text-gray-500">
        Every code is brand new and unique. Print the labels (40 per A4 page) and stick one on each bottle. Big batches are split into PDFs of {LABELS_PER_PDF.toLocaleString("en-IN")} labels.
        A damaged QR is replaced from the bottle&apos;s page in Overview.
      </p>
      <Table>
        <thead><tr><Th>Created</Th><Th>Codes</Th><Th>Range</Th><Th>Note</Th><Th>Download</Th></tr></thead>
        <tbody>{batches?.length ? batches.map((b) => <BatchRow key={b.id} b={b} />) : <TableEmpty colSpan={5}>No codes generated yet.</TableEmpty>}</tbody>
      </Table>
    </div>
  );
}
