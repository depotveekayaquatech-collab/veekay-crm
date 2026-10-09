import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Table, TableEmpty, Td, Th } from "@/components/ui/Table";
import { useBatches, useDeleteBatch, useDeleteCodes, when, type DeleteResult } from "@/features/bottles/api";

function Outcome({ r }: { r: DeleteResult }) {
  return (
    <div className="rounded-xl border border-surface-border bg-surface-subtle p-3 text-sm text-gray-700">
      <p>
        <b>{r.deleted.toLocaleString("en-IN")}</b> deleted{r.alreadyDeleted ? `, ${r.alreadyDeleted} were already deleted` : ""}.
      </p>
      {r.skippedInUse.length > 0 && (
        <p className="mt-1">
          Left alone because they are already in use (scanned): <span className="font-mono text-xs">{r.skippedInUse.slice(0, 20).join(", ")}{r.skippedInUse.length > 20 ? " …" : ""}</span>.
          Paste a code above to delete it on purpose.
        </p>
      )}
      {r.notFound.length > 0 && <p className="mt-1 text-status-warning">Not found: <span className="font-mono text-xs">{r.notFound.slice(0, 20).join(", ")}</span></p>}
    </div>
  );
}

/** Developer only. A deleted code stops working for good, but its record and scan history stay on file. */
export function DeleteCodes() {
  const [text, setText] = useState("");
  const [reason, setReason] = useState("");
  const [result, setResult] = useState<DeleteResult | null>(null);
  const del = useDeleteCodes();
  const delBatch = useDeleteBatch();
  const { data: batches } = useBatches(true);
  const serials = text.split(/[\s,;]+/).filter(Boolean);

  function confirmThen(message: string, run: () => void) {
    if (window.confirm(`${message}\n\nThe code(s) can never be scanned again. Their history is kept.`)) run();
  }

  return (
    <div className="flex flex-col gap-5">
      <p className="rounded-xl border border-status-warning bg-status-warning-soft px-4 py-3 text-sm text-gray-800">
        A deleted code can never be scanned or used again, and its number is never re-issued. <b>Nothing is erased</b>: the code, its reason and its whole scan history stay on file.
        Find them any time in Overview: search a code, or open the <b>Deleted</b> list.
      </p>

      <div className="flex flex-col gap-3 rounded-xl border border-surface-border bg-surface p-4 shadow-card">
        <label htmlFor="del-codes" className="text-[13px] font-semibold text-gray-700">Delete specific codes</label>
        <textarea
          id="del-codes"
          rows={4}
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="Paste codes, one per line or separated by commas, e.g. VK-7F3K-9Q2M"
          className="rounded-lg border border-surface-border bg-surface p-3 font-mono text-sm outline-none focus:ring-2"
        />
        <Input label="Reason (kept with the record)" value={reason} onChange={(e) => setReason(e.target.value)} placeholder="e.g. QR destroyed, misprinted, never used" />
        <div className="flex items-center gap-3">
          <Button
            variant="danger"
            disabled={serials.length === 0}
            isLoading={del.isPending}
            onClick={() => confirmThen(`Delete ${serials.length} code(s)?`, () => del.mutate({ serials, reason }, { onSuccess: (r) => { setResult(r); setText(""); } }))}
          >
            Delete {serials.length || ""} code{serials.length === 1 ? "" : "s"}
          </Button>
          {serials.length > 0 && <span className="text-xs text-gray-500">{serials.length.toLocaleString("en-IN")} entered</span>}
        </div>
        {result && <Outcome r={result} />}
      </div>

      <Table>
        <thead><tr><Th>Created</Th><Th>Codes</Th><Th>Range</Th><Th>Note</Th><Th>Delete</Th></tr></thead>
        <tbody>
          {batches?.length ? batches.map((b) => (
            <tr key={b.id}>
              <Td className="whitespace-nowrap">{when(b.createdAt)}</Td>
              <Td className="tabular-nums">{b.quantity.toLocaleString("en-IN")}</Td>
              <Td className="font-mono text-xs">{b.firstSerial}<br />{b.lastSerial}</Td>
              <Td>{b.note ?? "—"}</Td>
              <Td>
                <Button
                  size="sm"
                  variant="danger"
                  isLoading={delBatch.isPending && delBatch.variables?.batchId === b.id}
                  onClick={() => confirmThen("Delete every unused code of this batch? Codes already scanned are left alone.", () => delBatch.mutate({ batchId: b.id, reason }, { onSuccess: setResult }))}
                >
                  Delete unused
                </Button>
              </Td>
            </tr>
          )) : <TableEmpty colSpan={5}>No batches.</TableEmpty>}
        </tbody>
      </Table>
    </div>
  );
}
