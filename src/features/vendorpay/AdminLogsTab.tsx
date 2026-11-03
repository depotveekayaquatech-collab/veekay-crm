import { useState } from "react";
import { EmptyState } from "@/components/feedback/EmptyState";
import { ErrorState } from "@/components/feedback/ErrorState";
import { Skeleton } from "@/components/feedback/Skeleton";
import { Badge } from "@/components/ui/Badge";
import { Pagination } from "@/components/ui/Pagination";
import { Table, Td, Th } from "@/components/ui/Table";
import { ADMIN_PAGE_SIZE, useSyncLogs, type SyncLog } from "@/features/vendorpay/adminApi";
import { formatWhen } from "@/features/vendorpay/format";

const TONE = { SUCCESS: "success", PARTIAL: "warning", FAILED: "danger" } as const;
const LABEL = { SUCCESS: "Success", PARTIAL: "Some rows rejected", FAILED: "Failed" } as const;

const period = (l: SyncLog) => (l.periodFrom && l.periodTo ? `${l.periodFrom} to ${l.periodTo}` : "");

export function AdminLogsTab() {
  const [page, setPage] = useState(1);
  const { data, isLoading, isError, refetch } = useSyncLogs(page);

  if (isError) return <ErrorState message="Couldn't load the sync history." onRetry={() => void refetch()} />;
  if (isLoading || !data) return <Skeleton className="h-64 w-full" />;
  if (data.total === 0) return <EmptyState title="No syncs yet" description="Every call from Busy and every CSV import is listed here." />;

  return (
    <div className="flex flex-col gap-3">
      <Table className="min-w-[900px]">
        <thead>
          <tr>
            <Th>Time (India)</Th>
            <Th>From</Th>
            <Th>Status</Th>
            <Th className="text-right">Received</Th>
            <Th className="text-right">Added</Th>
            <Th className="text-right">Updated</Th>
            <Th className="text-right">Same</Th>
            <Th className="text-right">Removed</Th>
            <Th className="text-right">Unmatched</Th>
            <Th className="text-right">Rejected</Th>
            <Th>Note</Th>
          </tr>
        </thead>
        <tbody>
          {data.items.map((l) => (
            <tr key={l.id}>
              <Td className="whitespace-nowrap">{formatWhen(l.startedAt)}</Td>
              <Td className="whitespace-nowrap">
                {l.source === "CSV" ? "CSV upload" : "Busy"}
                {l.triggeredBy && <span className="block text-[11px] text-gray-500">{l.triggeredBy}</span>}
              </Td>
              <Td><Badge tone={TONE[l.status]}>{LABEL[l.status]}</Badge></Td>
              <Td className="text-right tabular-nums">{l.rowsReceived}</Td>
              <Td className="text-right tabular-nums">{l.rowsInserted}</Td>
              <Td className="text-right tabular-nums">{l.rowsUpdated}</Td>
              <Td className="text-right tabular-nums">{l.rowsUnchanged}</Td>
              <Td className="text-right tabular-nums">{l.rowsDeleted}</Td>
              <Td className="text-right tabular-nums">{l.rowsUnmatched}</Td>
              <Td className="text-right tabular-nums">{l.rowsRejected}</Td>
              <Td className="max-w-xs break-words text-xs text-gray-600">
                {[l.mode === "replace_period" ? `Replace ${period(l)}` : "", l.errorMessage ?? ""].filter(Boolean).join(". ")}
              </Td>
            </tr>
          ))}
        </tbody>
      </Table>
      <Pagination page={page} pageSize={ADMIN_PAGE_SIZE} total={data.total} onPageChange={setPage} />
    </div>
  );
}
