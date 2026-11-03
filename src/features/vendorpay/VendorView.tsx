import { EmptyState } from "@/components/feedback/EmptyState";
import { ErrorState } from "@/components/feedback/ErrorState";
import { Skeleton } from "@/components/feedback/Skeleton";
import { Badge } from "@/components/ui/Badge";
import { Table, Td, TableEmpty, Th } from "@/components/ui/Table";
import { useVendorDetail } from "@/features/vendorpay/api";
import { formatDay } from "@/features/vendorpay/format";
import { Amount, Stat } from "@/features/vendorpay/parts";
import { monthLabel } from "@/lib/months";

interface Props {
  vendorCode: string;
  month: string;
  onMonth: (month: string) => void;
}

export function VendorView({ vendorCode, month, onMonth }: Props) {
  const { data, isLoading, isError, refetch, isFetching } = useVendorDetail(vendorCode, month);

  if (isError) return <ErrorState message="Couldn't load this vendor." onRetry={() => void refetch()} />;
  const m = data?.month;
  const closingHint = m && Number(m.closing) < 0 ? "Paid ahead of bills" : m ? `Opening balance ${monthLabel(month)}: ` : undefined;

  return (
    <div className="flex flex-col gap-5" aria-busy={isFetching}>
      <section aria-label={`Figures for ${monthLabel(month)}`} className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="Month total (bills)" value={m?.monthTotal ?? null} loading={isLoading} />
        <Stat label="Paid" value={m?.paid ?? null} loading={isLoading} />
        <Stat label="Pending this month" value={m?.pending ?? null} loading={isLoading} hint={m && Number(m.pending) < 0 ? "Paid more than billed this month" : undefined} />
        <Stat label="Closing balance" value={m?.closing ?? null} loading={isLoading} hint={m && Number(m.closing) >= 0 ? undefined : closingHint} />
      </section>
      {m && (
        <p className="-mt-2 text-xs text-gray-500">
          Opening balance of {monthLabel(month)}: <Amount value={m.opening} />. Closing balance is the opening balance plus the month total, minus what was paid.
        </p>
      )}

      <section className="flex flex-col gap-2">
        <h3 className="text-sm font-bold text-heading">Month by month</h3>
        {isLoading || !data ? (
          <Skeleton className="h-48 w-full" />
        ) : (
          <Table>
            <thead>
              <tr>
                <Th>Month</Th>
                <Th className="text-right">Opening</Th>
                <Th className="text-right">Month total</Th>
                <Th className="text-right">Paid</Th>
                <Th className="text-right">Pending</Th>
                <Th className="text-right">Closing</Th>
              </tr>
            </thead>
            <tbody>
              {[...data.history].reverse().map((h) => (
                <tr key={h.month} className={`cursor-pointer hover:bg-surface-subtle/60 ${h.month === month ? "bg-brand-500/5" : ""}`} onClick={() => onMonth(h.month)} aria-current={h.month === month ? "true" : undefined}>
                  <Td className="font-semibold text-heading">
                    <button type="button" className="text-left hover:underline" onClick={(e) => { e.stopPropagation(); onMonth(h.month); }}>
                      {monthLabel(h.month)}
                    </button>
                  </Td>
                  <Td className="text-right"><Amount value={h.opening} /></Td>
                  <Td className="text-right"><Amount value={h.monthTotal} /></Td>
                  <Td className="text-right"><Amount value={h.paid} /></Td>
                  <Td className="text-right"><Amount value={h.pending} /></Td>
                  <Td className="text-right"><Amount value={h.closing} strong /></Td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}
      </section>

      <section className="flex flex-col gap-2">
        <h3 className="text-sm font-bold text-heading">Entries in {monthLabel(month)}</h3>
        {isLoading || !data ? (
          <Skeleton className="h-32 w-full" />
        ) : data.entries.length === 0 ? (
          <EmptyState title="No entries this month" description="Nothing was billed to or paid to this vendor in the selected month." />
        ) : (
          <>
            <Table>
              <thead>
                <tr>
                  <Th>Date</Th>
                  <Th>Type</Th>
                  <Th>Voucher no.</Th>
                  <Th>Narration</Th>
                  <Th className="text-right">Amount</Th>
                </tr>
              </thead>
              <tbody>
                {data.entries.map((e) => (
                  <tr key={`${e.entryType}-${e.voucherNo}`}>
                    <Td className="whitespace-nowrap">{formatDay(e.entryDate)}</Td>
                    <Td>
                      <Badge tone={e.entryType === "BILL" ? "info" : "success"}>{e.entryType === "BILL" ? "Bill" : "Payment"}</Badge>
                    </Td>
                    <Td className="tabular-nums">{e.voucherNo}</Td>
                    <Td className="max-w-xs break-words">{e.narration ?? ""}</Td>
                    <Td className="text-right"><Amount value={e.amount} /></Td>
                  </tr>
                ))}
                {data.entries.length === 0 && <TableEmpty colSpan={5} />}
              </tbody>
            </Table>
            {data.entriesTruncated && <p className="text-xs text-gray-500">Only the first 1,000 entries are shown.</p>}
          </>
        )}
      </section>
    </div>
  );
}
