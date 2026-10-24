import { useState } from "react";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Table, TableEmpty, Td, Th } from "@/components/ui/Table";
import { pushToast } from "@/lib/toast";
import { useRequestCheck, useReviewEntry, useVerifyEntry, type EntryRow } from "@/features/entries/api";
import { FLAG_LABEL, VERIFICATION_SHORT, VERIFICATION_TONE, fmtDay, fmtMoment, roleLabel } from "@/features/entries/format";

const REVIEW_TONE = { none: "neutral", reviewed: "success", flagged: "danger", needs_correction: "danger" } as const;
const REVIEW_LABEL = { none: "Not reviewed", reviewed: "Reviewed", flagged: "Flagged", needs_correction: "Needs correction" } as const;

/** The one-click actions a person's level allows on a row (the server decides what is allowed; `actions` only mirrors it). */
function RowActions({ row, onOpen }: { row: EntryRow; onOpen: (id: string) => void }) {
  const verify = useVerifyEntry();
  const review = useReviewEntry();
  const request = useRequestCheck();
  const [busy, setBusy] = useState<string | null>(null);
  const a = row.actions;
  const fail = (e: unknown) => pushToast(e instanceof Error ? e.message : "That didn't work.", "error");
  const run = (name: string, go: () => void) => { setBusy(name); go(); };
  const settle = { onSettled: () => setBusy(null), onError: fail };

  return (
    <div className="flex flex-wrap items-center justify-end gap-1.5">
      {a?.verify && <Button size="sm" isLoading={busy === "verify"} onClick={() => run("verify", () => verify.mutate({ entryId: row.entry_id }, settle))}>Verify</Button>}
      {a?.review && row.verification?.status === "submitted" && (
        <Button size="sm" isLoading={busy === "review"} onClick={() => run("review", () => review.mutate({ entryId: row.entry_id, action: "reviewed" }, settle))}>Review Myself</Button>
      )}
      {a?.request_check && <Button size="sm" variant="secondary" isLoading={busy === "request"} onClick={() => run("request", () => request.mutate({ entryId: row.entry_id }, settle))}>Request Team Lead to Check</Button>}
      <Button size="sm" variant="secondary" onClick={() => onOpen(row.entry_id)}>Open</Button>
    </div>
  );
}

/**
 * Entries as a date-wise table: the day opens the verification drawer, the store name narrows the list to that store, and each row carries the quick
 * actions the signed-in level may use.
 */
export function EntryResultsTable({ rows, onOpen, onPickStore, showStore = true }: {
  rows: EntryRow[]; onOpen: (id: string) => void; onPickStore?: (store: { id: string; name: string }) => void; showStore?: boolean;
}) {
  return (
    <Table>
      <thead>
        <tr>
          <Th>Date</Th>
          {showStore && <Th>Store</Th>}
          <Th>Employee</Th>
          <Th>Quantity</Th>
          <Th>Status</Th>
          <Th>Created</Th>
          <Th>Last change</Th>
          <Th className="text-right">Actions</Th>
        </tr>
      </thead>
      <tbody>
        {rows.length === 0 && <TableEmpty colSpan={showStore ? 8 : 7}>No entries match these filters.</TableEmpty>}
        {rows.map((r) => {
          const c = r.creator;
          const review = r.review?.status ?? "none";
          const status = r.verification?.status ?? "submitted";
          return (
            <tr key={r.entry_id}>
              <Td className="whitespace-nowrap">
                <button type="button" onClick={() => onOpen(r.entry_id)} title="Open the verification panel" className="font-semibold text-brand-600 underline-offset-2 hover:underline focus-visible:underline">
                  {fmtDay(r.order_date)}
                </button>
              </Td>
              {showStore && (
                <Td>
                  {onPickStore && r.store ? (
                    <button type="button" onClick={() => onPickStore({ id: r.store!.id, name: r.store!.name })} title="Show only this store, date by date" className="text-left font-semibold text-gray-900 hover:text-brand-600 hover:underline">
                      {r.store.name}
                    </button>
                  ) : <span className="font-semibold text-gray-900">{r.store?.name}</span>}
                  <span className="block text-xs text-gray-500">{r.store?.outlet_id}{r.store?.crm_code ? ` · ${r.store.crm_code}` : ""}{r.store?.entity ? ` · ${r.store.entity}` : ""}{r.store?.status && r.store.status !== "LIVE" ? ` · ${r.store.status}` : ""}</span>
                </Td>
              )}
              <Td>
                {c?.verified ? (
                  <>
                    <span className="font-medium text-gray-900">{c.name}</span>
                    <span className="block text-xs text-gray-500">{c.code} · {roleLabel(c.role)}</span>
                  </>
                ) : (
                  <>
                    <Badge tone="warning">Not verified</Badge>
                    <span className="block text-xs text-gray-500">{c?.last_recorded_marker ? `last marker: ${c.last_recorded_marker}` : "no creator on record"}</span>
                  </>
                )}
              </Td>
              <Td>
                <span className="text-base font-bold tabular-nums text-gray-900">{r.employee_count}</span>
                {r.cash_adjustment ? <span className="block text-xs text-gray-500">+{r.cash_adjustment} adj.</span> : null}
              </Td>
              <Td>
                <div className="flex flex-wrap items-center gap-1">
                  <Badge tone={VERIFICATION_TONE[status]} dot>{VERIFICATION_SHORT[status]}</Badge>
                  {r.verification?.check_requested && <Badge tone="warning">Verification requested</Badge>}
                  {review !== "none" && review !== "reviewed" && <Badge tone={REVIEW_TONE[review]}>{REVIEW_LABEL[review]}</Badge>}
                  {(r.flags ?? []).filter((f) => !["flagged", "needs_correction", "unverified_creator"].includes(f)).map((f) => (
                    <Badge key={f} tone="neutral">{FLAG_LABEL[f] ?? f}</Badge>
                  ))}
                </div>
              </Td>
              <Td className="whitespace-nowrap text-xs">{fmtMoment(r.created_at)}</Td>
              <Td className="text-xs">
                {r.last_modified ? (
                  <>
                    <span className="font-medium text-gray-900">{r.last_modified.by_name ?? "unknown"}</span>
                    <span className="block text-gray-500">{roleLabel(r.last_modified.role)} · {fmtMoment(r.last_modified.at)}</span>
                  </>
                ) : (
                  <span className="text-gray-400">never changed</span>
                )}
              </Td>
              <Td className="text-right"><RowActions row={r} onOpen={onOpen} /></Td>
            </tr>
          );
        })}
      </tbody>
    </Table>
  );
}
