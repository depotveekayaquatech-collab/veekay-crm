import { useState } from "react";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import { Skeleton } from "@/components/feedback/Skeleton";
import { ErrorState } from "@/components/feedback/ErrorState";
import { EmptyState } from "@/components/feedback/EmptyState";
import { SearchBox, SegmentedControl } from "@/features/orders/ui";
import { fmtDay } from "@/features/attendance/format";
import { LEAVE_LABEL, LEAVE_TONE, useAllLeaves, useLeaveMutations, type Leave } from "@/features/attendance/api";

function ReviewModal({ leave, approve, onClose }: { leave: Leave; approve: boolean; onClose: () => void }) {
  const { review } = useLeaveMutations();
  const [note, setNote] = useState("");
  async function go() {
    try {
      await review.mutateAsync({ id: leave.id, approve, note });
      onClose();
    } catch {
      /* shown by the API layer */
    }
  }
  return (
    <Modal
      open
      onClose={onClose}
      size="sm"
      title={approve ? "Approve leave" : "Reject leave"}
      description={`${leave.person?.name} · ${leave.days} day${leave.days === 1 ? "" : "s"} · ${leave.startDate === leave.endDate ? leave.startDate : `${leave.startDate} → ${leave.endDate}`}`}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={review.isPending}>Cancel</Button>
          <Button variant={approve ? "primary" : "danger"} onClick={() => void go()} isLoading={review.isPending}>
            {approve ? "Approve" : "Reject"}
          </Button>
        </>
      }
    >
      <label className="flex flex-col gap-1.5 text-sm font-medium text-gray-700">
        Note to the employee <span className="font-normal text-gray-400">(optional)</span>
        <textarea
          value={note}
          onChange={(e) => setNote(e.target.value)}
          rows={3}
          maxLength={500}
          autoFocus
          className="rounded-md border border-surface-border bg-surface px-3 py-2 text-sm font-normal shadow-sm outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20"
        />
      </label>
    </Modal>
  );
}

export function LeaveRequestsView() {
  const [status, setStatus] = useState("PENDING");
  const [q, setQ] = useState("");
  const [acting, setActing] = useState<{ leave: Leave; approve: boolean } | null>(null);
  const { data, isLoading, isError, refetch } = useAllLeaves(status, q);

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-center gap-3">
        <SegmentedControl
          label="Status"
          value={status}
          onChange={setStatus}
          options={[
            { value: "PENDING", label: `Pending${data?.pending ? ` (${data.pending})` : ""}` },
            { value: "APPROVED", label: "Approved" },
            { value: "REJECTED", label: "Rejected" },
            { value: "", label: "All" },
          ]}
        />
        <SearchBox value={q} onChange={setQ} placeholder="Search name or ID" className="w-full sm:ml-auto sm:w-64" />
      </div>

      {isLoading && <Skeleton className="h-48" />}
      {isError && <ErrorState message="Couldn't load leave requests." onRetry={() => refetch()} />}
      {data && data.items.length === 0 && (
        <EmptyState title={status === "PENDING" ? "Nothing waiting for approval" : "No requests"} description="New leave requests from employees appear here." />
      )}

      {data && data.items.length > 0 && (
        <div className="overflow-x-auto rounded-xl border border-surface-border bg-surface shadow-card">
          <table className="w-full min-w-[760px] text-sm">
            <thead>
              <tr className="bg-surface-subtle text-left text-[11px] font-bold uppercase tracking-wider text-gray-500">
                <th className="px-4 py-3">Employee</th>
                <th className="px-3 py-3">Dates</th>
                <th className="px-3 py-3">Type</th>
                <th className="px-3 py-3 text-right">Days</th>
                <th className="px-3 py-3">Status</th>
                <th className="px-4 py-3 text-right" />
              </tr>
            </thead>
            <tbody>
              {data.items.map((l) => (
                <tr key={l.id} className="border-t border-surface-border/70 align-top">
                  <td className="px-4 py-3">
                    <div className="font-medium text-gray-900">{l.person?.name}</div>
                    <div className="text-[11px] text-gray-500">{[l.person?.code, l.person?.platform, l.person?.region].filter(Boolean).join(" · ")}</div>
                  </td>
                  <td className="px-3 py-3">
                    <div className="font-medium text-gray-900">{l.startDate === l.endDate ? fmtDay(l.startDate) : `${fmtDay(l.startDate)} → ${fmtDay(l.endDate)}`}</div>
                    <div className="max-w-[16rem] truncate text-xs text-gray-500" title={l.reason}>{l.reason}</div>
                  </td>
                  <td className="px-3 py-3 text-gray-700">{LEAVE_LABEL[l.leaveType]}{l.halfDay ? " · half" : ""}</td>
                  <td className="px-3 py-3 text-right font-semibold tabular-nums">{l.days}</td>
                  <td className="px-3 py-3">
                    <Badge tone={LEAVE_TONE[l.status]}>{l.status.charAt(0) + l.status.slice(1).toLowerCase()}</Badge>
                    {l.reviewedByName && <div className="mt-0.5 text-[11px] text-gray-500">by {l.reviewedByName}</div>}
                  </td>
                  <td className="px-4 py-3 text-right">
                    {l.status === "PENDING" && (
                      <div className="flex justify-end gap-2">
                        <Button size="sm" onClick={() => setActing({ leave: l, approve: true })}>Approve</Button>
                        <Button size="sm" variant="secondary" onClick={() => setActing({ leave: l, approve: false })}>Reject</Button>
                      </div>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {acting && <ReviewModal leave={acting.leave} approve={acting.approve} onClose={() => setActing(null)} />}
    </div>
  );
}
