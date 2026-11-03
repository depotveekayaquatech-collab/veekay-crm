import { Table, Td, Th } from "@/components/ui/Table";
import { inr } from "@/features/cash/api";
import type { SyncResult } from "@/features/vendorpay/adminApi";

function Count({ label, value, tone = "" }: { label: string; value: number; tone?: string }) {
  return (
    <div className="rounded-xl border border-surface-border bg-surface px-3 py-2.5">
      <p className="text-[11px] font-bold text-gray-500">{label}</p>
      <p className={`mt-0.5 text-xl font-bold tabular-nums ${tone || "text-heading"}`}>{value.toLocaleString("en-IN")}</p>
    </div>
  );
}

/** What a sync (or its dry run) did: the counts, the rows that were turned away and why, and the codes that matched no vendor. */
export function SyncResultPanel({ result, dryRun }: { result: SyncResult; dryRun: boolean }) {
  return (
    <div className="flex flex-col gap-4">
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-5">
        <Count label={dryRun ? "Will be added" : "Added"} value={result.inserted} />
        <Count label={dryRun ? "Will be updated" : "Updated"} value={result.updated} />
        <Count label="Already up to date" value={result.unchanged} />
        <Count label="Unknown vendor code" value={result.unmatched} tone={result.unmatched ? "text-status-warning" : ""} />
        <Count label="Rejected" value={result.rejected} tone={result.rejected ? "text-status-danger" : ""} />
      </div>

      {result.unmatched > 0 && (
        <p className="rounded-xl bg-status-warning-soft px-4 py-3 text-sm text-status-warning">
          {result.unmatched} row(s) have a vendor code that is not a vendor here ({result.unmatchedCodes.join(", ")}). They are kept, not lost: add the vendor or map the code on the “Unmatched codes” tab.
        </p>
      )}

      {result.errors.length > 0 && (
        <div className="flex flex-col gap-2">
          <h4 className="text-sm font-bold text-heading">Rejected rows ({result.rejected})</h4>
          <div className="max-h-72 overflow-auto">
            <Table>
              <thead>
                <tr>
                  <Th>Row</Th>
                  <Th>Voucher</Th>
                  <Th>Problem</Th>
                </tr>
              </thead>
              <tbody>
                {result.errors.map((e) => (
                  <tr key={`${e.row}-${e.message}`}>
                    <Td className="tabular-nums">{e.row}</Td>
                    <Td className="tabular-nums">{e.voucherNo}</Td>
                    <Td>{e.message}</Td>
                  </tr>
                ))}
              </tbody>
            </Table>
          </div>
          {result.errorsTruncated && <p className="text-xs text-gray-500">Only the first {result.errors.length} problems are listed.</p>}
        </div>
      )}

      {result.sample.length > 0 && (
        <div className="flex flex-col gap-2">
          <h4 className="text-sm font-bold text-heading">First rows read</h4>
          <Table>
            <thead>
              <tr>
                <Th>Row</Th>
                <Th>Vendor code</Th>
                <Th>Date</Th>
                <Th>Type</Th>
                <Th>Voucher</Th>
                <Th className="text-right">Amount</Th>
              </tr>
            </thead>
            <tbody>
              {result.sample.map((s) => (
                <tr key={s.row}>
                  <Td className="tabular-nums">{s.row}</Td>
                  <Td className="tabular-nums">{s.vendorCode ?? "none"}</Td>
                  <Td className="tabular-nums">{s.date}</Td>
                  <Td>{s.type}</Td>
                  <Td className="tabular-nums">{s.voucherNo}</Td>
                  <Td className="text-right tabular-nums">{inr(s.amount)}</Td>
                </tr>
              ))}
            </tbody>
          </Table>
        </div>
      )}
    </div>
  );
}
