import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Table, TableEmpty, Td, Th } from "@/components/ui/Table";
import type { EntryRow } from "@/features/entries/api";
import { FLAG_LABEL, fmtDay, fmtMoment, roleLabel } from "@/features/entries/format";

const REVIEW_TONE = { none: "neutral", reviewed: "success", flagged: "danger", needs_correction: "danger" } as const;
const REVIEW_LABEL = { none: "Not reviewed", reviewed: "Reviewed", flagged: "Flagged", needs_correction: "Needs correction" } as const;

/** Entries as a table: who created each one and when, who last changed it, and a button for its full history. */
export function EntryResultsTable({ rows, onOpen, showStore = true }: { rows: EntryRow[]; onOpen: (id: string) => void; showStore?: boolean }) {
  return (
    <Table>
      <thead>
        <tr>
          {showStore && <Th>Store</Th>}
          <Th>Day</Th>
          <Th>Number</Th>
          <Th>Created by</Th>
          <Th>Created (server time)</Th>
          <Th>Last change</Th>
          <Th>Status</Th>
          <Th className="text-right">History</Th>
        </tr>
      </thead>
      <tbody>
        {rows.length === 0 && <TableEmpty colSpan={showStore ? 8 : 7}>No entries match these filters.</TableEmpty>}
        {rows.map((r) => {
          const c = r.creator;
          const review = r.review?.status ?? "none";
          return (
            <tr key={r.entry_id}>
              {showStore && (
                <Td>
                  <span className="font-semibold text-gray-900">{r.store?.name}</span>
                  <span className="block text-xs text-gray-500">{r.store?.outlet_id}{r.store?.crm_code ? ` · ${r.store.crm_code}` : ""}{r.store?.status && r.store.status !== "LIVE" ? ` · ${r.store.status}` : ""}</span>
                </Td>
              )}
              <Td className="whitespace-nowrap">{fmtDay(r.order_date)}</Td>
              <Td>
                <span className="text-base font-bold tabular-nums text-gray-900">{r.employee_count}</span>
                {r.cash_adjustment ? <span className="block text-xs text-gray-500">+{r.cash_adjustment} adj.</span> : null}
              </Td>
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
              <Td>
                <div className="flex flex-wrap items-center gap-1">
                  <Badge tone={REVIEW_TONE[review]}>{REVIEW_LABEL[review]}</Badge>
                  {(r.flags ?? []).filter((f) => !["flagged", "needs_correction", "unverified_creator"].includes(f)).map((f) => (
                    <Badge key={f} tone="neutral">{FLAG_LABEL[f] ?? f}</Badge>
                  ))}
                </div>
              </Td>
              <Td className="text-right">
                <Button size="sm" variant="secondary" onClick={() => onOpen(r.entry_id)}>Open</Button>
              </Td>
            </tr>
          );
        })}
      </tbody>
    </Table>
  );
}
