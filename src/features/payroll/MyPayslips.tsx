import { useState } from "react";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Skeleton } from "@/components/feedback/Skeleton";
import { ErrorState } from "@/components/feedback/ErrorState";
import { EmptyState } from "@/components/feedback/EmptyState";
import { money, useMyPayslips, type MyPayslip } from "@/features/payroll/api";
import { DayTable } from "@/features/payroll/payslipParts";

const longDate = (iso: string) => new Date(iso).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });

function PayslipCard({ slip, startOpen }: { slip: MyPayslip; startOpen: boolean }) {
  const [open, setOpen] = useState(startOpen);
  return (
    <section className="rounded-xl border border-surface-border bg-surface shadow-card">
      <header className="flex flex-wrap items-center justify-between gap-3 p-4">
        <div>
          <h3 className="text-base font-extrabold text-heading">{slip.monthLabel}</h3>
          <p className="text-xs text-gray-500">Paid on {longDate(slip.paidAt)} · {slip.paidDays} of {slip.daysInMonth} days</p>
        </div>
        <div className="flex items-center gap-3">
          <Badge tone="success" dot>Paid</Badge>
          <p className="text-xl font-extrabold tabular-nums text-heading">{money(slip.amount)}</p>
          <Button size="sm" variant="secondary" onClick={() => setOpen((o) => !o)} aria-expanded={open}>{open ? "Hide days" : "Day-wise attendance"}</Button>
        </div>
      </header>
      {open && (
        <div className="border-t border-surface-border/80 p-4">
          <p className="mb-3 text-xs text-gray-500">
            Monthly salary {money(slip.monthlySalary)} ÷ {slip.daysInMonth} days × {slip.paidDays} paid days. Weekly offs and approved paid leave count as paid days.
          </p>
          <DayTable days={slip.days ?? []} readOnly />
        </div>
      )}
    </section>
  );
}

/** Attendance → My payslips: every salary paid to the signed-in employee, with the day-wise attendance it was based on. */
export function MyPayslips() {
  const { data, isLoading, isError, refetch } = useMyPayslips();
  if (isLoading) return <Skeleton className="h-40" />;
  if (isError || !data) return <ErrorState message="Couldn't load your payslips." onRetry={() => refetch()} />;
  if (data.items.length === 0) return <EmptyState title="No payslips yet" description="Your payslip appears here once your salary has been paid." />;
  return (
    <div className="flex flex-col gap-4">
      {data.items.map((s, i) => <PayslipCard key={s.id} slip={s} startOpen={i === 0} />)}
    </div>
  );
}
