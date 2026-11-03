import { EmptyState } from "@/components/feedback/EmptyState";
import { ErrorState } from "@/components/feedback/ErrorState";
import { Skeleton } from "@/components/feedback/Skeleton";
import { Pagination } from "@/components/ui/Pagination";
import { Table, Td, Th } from "@/components/ui/Table";
import { PAGE_SIZE, useSummary, type SortDirection, type SortKey, type SummaryRow } from "@/features/vendorpay/api";
import { Amount } from "@/features/vendorpay/parts";

interface Props {
  month: string;
  sort: SortKey;
  direction: SortDirection;
  page: number;
  onSort: (key: SortKey) => void;
  onPage: (page: number) => void;
  onOpenVendor: (code: string) => void;
}

const COLUMNS: { key: SortKey; label: string; numeric: boolean }[] = [
  { key: "name", label: "Vendor name", numeric: false },
  { key: "city", label: "City", numeric: false },
  { key: "code", label: "Code", numeric: false },
  { key: "month_total", label: "Month total", numeric: true },
  { key: "paid", label: "Paid", numeric: true },
  { key: "pending", label: "Pending", numeric: true },
  { key: "closing", label: "Closing balance", numeric: true },
];

function SortHeader({ column, active, direction, onSort }: { column: (typeof COLUMNS)[number]; active: boolean; direction: SortDirection; onSort: (k: SortKey) => void }) {
  return (
    <Th className={column.numeric ? "text-right" : ""} aria-sort={active ? (direction === "asc" ? "ascending" : "descending") : "none"}>
      <button type="button" onClick={() => onSort(column.key)} className="inline-flex items-center gap-1 font-semibold hover:text-gray-800">
        {column.label}
        <span aria-hidden="true" className={active ? "text-brand-600" : "text-gray-300"}>
          {active && direction === "desc" ? "▼" : "▲"}
        </span>
      </button>
    </Th>
  );
}

function VendorCard({ row, onOpen }: { row: SummaryRow; onOpen: (code: string) => void }) {
  return (
    <button type="button" onClick={() => onOpen(row.vendorCode)} className="w-full rounded-xl border border-surface-border bg-surface p-4 text-left shadow-card">
      <p className="font-bold text-heading">{row.name}</p>
      <p className="text-xs text-gray-500">
        {row.city ? `${row.city}, ` : ""}
        {row.vendorCode}
      </p>
      <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
        {(
          [
            ["Month total", row.monthTotal],
            ["Paid", row.paid],
            ["Pending", row.pending],
            ["Closing balance", row.closing],
          ] as const
        ).map(([label, value]) => (
          <div key={label}>
            <dt className="text-[11px] font-semibold text-gray-500">{label}</dt>
            <dd>
              <Amount value={value} />
            </dd>
          </div>
        ))}
      </dl>
    </button>
  );
}

export function AllVendorsView({ month, sort, direction, page, onSort, onPage, onOpenVendor }: Props) {
  const { data, isLoading, isError, refetch } = useSummary(month, sort, direction, page);

  if (isError) return <ErrorState message="Couldn't load the vendor figures." onRetry={() => void refetch()} />;
  if (isLoading || !data) {
    return (
      <div className="flex flex-col gap-2" aria-busy="true" aria-label="Loading vendors">
        {Array.from({ length: 6 }, (_, i) => (
          <Skeleton key={i} className="h-12 w-full" />
        ))}
      </div>
    );
  }
  if (data.total === 0) {
    return <EmptyState title="No vendors yet" description="Vendors appear here once an administrator adds them or approves the codes that arrive from Busy." />;
  }

  const t = data.totals;
  return (
    <div className="flex flex-col gap-3">
      <div className="hidden sm:block">
        <Table>
          <thead>
            <tr>
              {COLUMNS.map((c) => (
                <SortHeader key={c.key} column={c} active={sort === c.key} direction={direction} onSort={onSort} />
              ))}
            </tr>
          </thead>
          <tbody>
            {data.items.map((r) => (
              <tr key={r.vendorCode} className="cursor-pointer hover:bg-surface-subtle/60" onClick={() => onOpenVendor(r.vendorCode)}>
                <Td className="font-semibold text-heading">
                  <button type="button" className="text-left hover:underline" onClick={(e) => { e.stopPropagation(); onOpenVendor(r.vendorCode); }}>
                    {r.name}
                  </button>
                </Td>
                <Td>{r.city ?? ""}</Td>
                <Td className="tabular-nums">{r.vendorCode}</Td>
                <Td className="text-right"><Amount value={r.monthTotal} /></Td>
                <Td className="text-right"><Amount value={r.paid} /></Td>
                <Td className="text-right"><Amount value={r.pending} /></Td>
                <Td className="text-right"><Amount value={r.closing} strong /></Td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr className="bg-surface-subtle/80 font-bold text-heading">
              <Td colSpan={3}>Total, all {t.vendors} vendors</Td>
              <Td className="text-right"><Amount value={t.monthTotal} strong /></Td>
              <Td className="text-right"><Amount value={t.paid} strong /></Td>
              <Td className="text-right"><Amount value={t.pending} strong /></Td>
              <Td className="text-right"><Amount value={t.closing} strong /></Td>
            </tr>
          </tfoot>
        </Table>
      </div>

      <div className="flex flex-col gap-2 sm:hidden">
        {data.items.map((r) => (
          <VendorCard key={r.vendorCode} row={r} onOpen={onOpenVendor} />
        ))}
        <div className="rounded-xl bg-surface-subtle p-4 text-sm font-bold text-heading">
          <p>Total, all {t.vendors} vendors</p>
          <p className="mt-1 text-xs font-semibold text-gray-600">
            Month total <Amount value={t.monthTotal} /> · Paid <Amount value={t.paid} /> · Pending <Amount value={t.pending} /> · Closing <Amount value={t.closing} />
          </p>
        </div>
      </div>

      <Pagination page={page} pageSize={PAGE_SIZE} total={data.total} onPageChange={onPage} />
    </div>
  );
}
