import { useState, type FormEvent } from "react";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { SelectField } from "@/components/ui/Dropdown";
import { Input } from "@/components/ui/Input";
import { Modal } from "@/components/ui/Modal";
import { Skeleton } from "@/components/feedback/Skeleton";
import { ErrorState } from "@/components/feedback/ErrorState";
import { EmptyState } from "@/components/feedback/EmptyState";
import { IconEdit } from "@/components/ui/icons";
import {
  money, usePayrollMutations, usePayroll, usePayslip,
  type PayPeriod, type PayrollRow, type PayslipDetail, type PayMark, type PayStatus, type WindowState,
} from "@/features/payroll/api";
import { DayTable } from "@/features/payroll/payslipParts";
import { previewDays, type Pending } from "@/features/payroll/payslipMath";

const field = "h-10 w-full rounded-lg border border-surface-border bg-surface px-3 text-sm shadow-sm outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20";
const longDate = (iso: string) => new Date(`${iso}T12:00:00`).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });
const monthName = (m: string) => new Date(`${m}-01T12:00:00`).toLocaleDateString("en-IN", { month: "long", year: "numeric" });

const WINDOW: Record<WindowState, { label: string; tone: "success" | "warning" | "neutral" }> = {
  OPEN: { label: "Payment window open", tone: "success" },
  UPCOMING: { label: "Opens on release date", tone: "warning" },
  CLOSED: { label: "Window closed", tone: "neutral" },
};
const STATUS: Record<PayStatus, { label: string; tone: "success" | "info" | "warning" }> = {
  PAID: { label: "Paid", tone: "success" },
  READY: { label: "To pay", tone: "info" },
  NO_SALARY: { label: "No salary set", tone: "warning" },
};

function PeriodModal({ month, period, onClose }: { month: string; period: PayPeriod; onClose: () => void }) {
  const { period: save } = usePayrollMutations(month);
  const [date, setDate] = useState(period.releaseDate);
  const [days, setDays] = useState(String(period.windowDays));
  const n = Number(days);
  const valid = Boolean(date) && Number.isInteger(n) && n >= 1 && n <= 31;

  function submit(e: FormEvent) {
    e.preventDefault();
    if (!valid || save.isPending) return;
    save.mutate({ releaseDate: date, windowDays: n }, { onSuccess: onClose });
  }
  return (
    <Modal
      open
      onClose={onClose}
      title="Salary release date"
      description={`When salary for ${monthName(month)} is released, and for how many days from then you can mark it as paid.`}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
          <Button type="submit" form="period-form" isLoading={save.isPending} disabled={!valid}>Save</Button>
        </>
      }
    >
      <form id="period-form" onSubmit={submit} className="grid gap-4 sm:grid-cols-2">
        <Input label="Release date" type="date" value={date} onChange={(e) => setDate(e.target.value)} required />
        <Input label="Days the window stays open" type="number" min={1} max={31} value={days} onChange={(e) => setDays(e.target.value)} hint="Counting the release date itself." required />
      </form>
    </Modal>
  );
}

/** One employee's salary: type it, save it. Months already paid keep what they were paid. */
function SalaryEditor({ month, row }: { month: string; row: { userId: string; monthlySalary: number | null; status: PayStatus } }) {
  const { salary } = usePayrollMutations(month);
  const [text, setText] = useState(row.monthlySalary?.toString() ?? "");
  const parsed = text.trim() === "" ? null : Number(text);
  const invalid = parsed !== null && (!Number.isFinite(parsed) || parsed < 0 || parsed > 10_000_000);
  const unchanged = parsed === row.monthlySalary;
  const locked = row.status === "PAID";
  return (
    <div className="flex items-end gap-2">
      <label className="flex flex-col gap-1 text-[11px] font-bold text-gray-500">
        Monthly salary (₹)
        <input
          className={`${field} w-40 normal-case tracking-normal`}
          inputMode="decimal"
          value={text}
          onChange={(e) => setText(e.target.value.replace(/[^\d.]/g, ""))}
          placeholder="e.g. 25000"
          disabled={locked}
          aria-invalid={invalid}
        />
      </label>
      {!locked && (
        <Button size="sm" variant="secondary" disabled={invalid || unchanged} isLoading={salary.isPending} onClick={() => salary.mutate({ userId: row.userId, monthlySalary: parsed })}>
          Save salary
        </Button>
      )}
    </div>
  );
}

function PayslipBody({ month, detail, onClose }: { month: string; detail: PayslipDetail; onClose: () => void }) {
  const { marks, pay } = usePayrollMutations(month);
  const [pending, setPending] = useState<Pending>({});
  const [confirming, setConfirming] = useState(false);
  const paid = detail.status === "PAID";

  const changes = Object.entries(pending).filter(([date, m]) => m !== (detail.days.find((d) => d.date === date)?.mark ?? "AUTO"));
  const dirty = changes.length > 0;
  const paidDays = dirty ? previewDays(detail.days, pending) : detail.paidDays;
  const amount = detail.monthlySalary === null ? null : dirty ? Math.round((detail.monthlySalary * paidDays * 100) / detail.daysInMonth) / 100 : detail.amount;

  function save() {
    marks.mutate({ userId: detail.person.userId, marks: changes.map(([date, m]) => ({ date, mark: m === "AUTO" ? null : (m as PayMark) })) }, { onSuccess: () => setPending({}) });
  }
  const blocker = paid ? null
    : detail.monthlySalary === null ? "Set the monthly salary to pay."
    : dirty ? "Save the day marks before paying."
    : detail.period.state === "UPCOMING" ? `Payment opens on ${longDate(detail.period.releaseDate)}.`
    : detail.period.state === "CLOSED" ? `The window closed on ${longDate(detail.period.closesOn)}. Change the release date to pay now.`
    : (amount ?? 0) <= 0 ? "No paid days, so nothing to pay." : null;

  return (
    <Modal
      open
      onClose={onClose}
      size="lg"
      title={`Payslip · ${detail.person.fullName}`}
      description={`${detail.person.employeeCode} · ${detail.monthLabel}`}
      footer={
        paid ? (
          <Button variant="secondary" onClick={onClose}>Close</Button>
        ) : confirming ? (
          <>
            <span className="mr-auto text-sm font-semibold text-gray-800">Pay {money(amount)} to {detail.person.fullName}?</span>
            <Button variant="secondary" onClick={() => setConfirming(false)}>Back</Button>
            <Button isLoading={pay.isPending} onClick={() => pay.mutate(detail.person.userId, { onSuccess: onClose })}>Yes, mark as paid</Button>
          </>
        ) : (
          <>
            {blocker && <span className="mr-auto text-xs text-gray-500">{blocker}</span>}
            <Button variant="secondary" onClick={onClose}>Close</Button>
            <Button variant="secondary" onClick={save} isLoading={marks.isPending} disabled={!dirty}>Save days{dirty ? ` (${changes.length})` : ""}</Button>
            <Button onClick={() => setConfirming(true)} disabled={Boolean(blocker)}>Pay {money(amount)}</Button>
          </>
        )
      }
    >
      <div className="flex flex-col gap-4">
        <div className="grid gap-3 sm:grid-cols-4">
          {[
            ["Monthly salary", money(detail.monthlySalary)],
            ["Per day", money(detail.perDay)],
            ["Paid days", `${paidDays} of ${detail.daysInMonth}`],
            [paid ? "Paid amount" : "Amount to pay", money(amount)],
          ].map(([l, v], i) => (
            <div key={l} className={`rounded-xl border p-3 ${i === 3 ? "border-brand-500/40 bg-brand-500/5" : "border-surface-border bg-surface"}`}>
              <p className="text-[11px] font-bold text-gray-500">{l}</p>
              <p className="mt-1 text-lg font-extrabold tabular-nums text-heading">{v}</p>
            </div>
          ))}
        </div>
        {paid && detail.payslip && (
          <p className="rounded-lg bg-status-success/10 px-3 py-2 text-sm text-gray-700">
            Paid on {new Date(detail.payslip.paidAt).toLocaleString("en-IN")}{detail.payslip.paidBy ? ` by ${detail.payslip.paidBy}` : ""}. The figures below are frozen.
          </p>
        )}
        <SalaryEditor month={month} row={{ userId: detail.person.userId, monthlySalary: detail.monthlySalary, status: detail.status }} />
        <p className="text-xs text-gray-500">
          Look at each day's timings and choose <b>Full day</b>, <b>Half day</b> or <b>Unpaid</b>; <b>Auto</b> counts a check-in as a full day, a Sunday off as paid, and approved paid leave as paid.
        </p>
        <DayTable days={detail.days} pending={pending} readOnly={paid} onMark={(date, m) => setPending((p) => ({ ...p, [date]: m }))} />
      </div>
    </Modal>
  );
}

function PayslipModal({ month, userId, onClose }: { month: string; userId: string; onClose: () => void }) {
  const { data, isLoading, isError, refetch } = usePayslip(month, userId);
  if (isLoading) return <Modal open onClose={onClose} size="lg" title="Payslip"><Skeleton className="h-64" /></Modal>;
  if (isError || !data) return <Modal open onClose={onClose} size="lg" title="Payslip"><ErrorState message="Couldn't load this payslip." onRetry={() => refetch()} /></Modal>;
  // starting afresh whenever what is saved changes keeps the pending choices honest
  const key = `${data.monthlySalary}|${data.status}|${data.days.map((d) => d.mark ?? "-").join("")}`;
  return <PayslipBody key={key} month={month} detail={data} onClose={onClose} />;
}

/** Attendance → Payslips (admins with payroll.manage): salaries, the release date, day marks and paying. */
export function PayslipView() {
  const [month, setMonth] = useState("");
  const [q, setQ] = useState("");
  const [openUser, setOpenUser] = useState<string | null>(null);
  const [editPeriod, setEditPeriod] = useState(false);
  const { data, isLoading, isError, error, refetch } = usePayroll(month);
  const shownMonth = data?.month ?? month;

  const needle = q.trim().toLowerCase();
  const rows: PayrollRow[] = (data?.rows ?? []).filter((r) => !needle || r.fullName.toLowerCase().includes(needle) || r.employeeCode.toLowerCase().includes(needle));

  return (
    <div className="flex flex-col gap-5">
      {isLoading && <Skeleton className="h-64" />}
      {isError && <ErrorState message={error instanceof Error ? error.message : "Couldn't load payroll."} onRetry={() => refetch()} />}
      {data && (
        <>
          <section className="flex flex-wrap items-center justify-between gap-4 rounded-xl border border-surface-border bg-surface p-4 shadow-card">
            <div className="flex flex-wrap items-center gap-4">
              <SelectField className="h-10 rounded-lg border border-surface-border bg-surface px-3 text-sm shadow-sm" value={shownMonth} onChange={(e) => setMonth(e.target.value)} aria-label="Salary month">
                {data.months.map((m) => <option key={m} value={m}>{monthName(m)}</option>)}
              </SelectField>
              <div>
                <p className="text-[11px] font-bold text-gray-500">Salary release date</p>
                <p className="text-sm font-bold text-gray-900">
                  {longDate(data.period.releaseDate)} <span className="font-normal text-gray-500">· open for {data.period.windowDays} day{data.period.windowDays === 1 ? "" : "s"}, until {longDate(data.period.closesOn)}</span>
                </p>
              </div>
              <Badge dot tone={WINDOW[data.period.state].tone}>{WINDOW[data.period.state].label}</Badge>
            </div>
            <Button variant="secondary" onClick={() => setEditPeriod(true)}><IconEdit className="h-4 w-4" /> Change date</Button>
          </section>

          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            {[
              ["To pay", `${data.summary.ready}`, money(data.summary.payableTotal)],
              ["Paid", `${data.summary.paid}`, money(data.summary.paidTotal)],
              ["No salary set", `${data.summary.noSalary}`, "set it on the payslip"],
              ["Employees", `${data.summary.employees}`, `${data.monthLabel}`],
            ].map(([l, v, hint]) => (
              <div key={l} className="rounded-xl border border-surface-border bg-surface p-4 shadow-card">
                <p className="text-[11px] font-bold text-gray-500">{l}</p>
                <p className="mt-1 text-2xl font-extrabold tabular-nums text-heading">{v}</p>
                <p className="mt-0.5 text-xs text-gray-500">{hint}</p>
              </div>
            ))}
          </div>

          <input className={`${field} sm:max-w-xs`} value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search name or employee ID" aria-label="Search employees" />

          {rows.length === 0 ? (
            <EmptyState title="No employees" description={data.rows.length ? "Nobody matches the search." : "There are no employees on the attendance list for this month."} />
          ) : (
            <div className="stacked-table overflow-x-auto rounded-xl border border-surface-border bg-surface shadow-card">
              <table className="w-full min-w-[820px] border-collapse text-sm">
                <thead>
                  <tr className="bg-surface-subtle/80 text-left text-[11px] font-bold text-gray-500">
                    {["Employee", "Salary", "Days present", "Paid days", "Amount", "Status", ""].map((h) => (
                      <th key={h} className="border-b border-surface-border px-3 py-3 first:pl-4">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r) => (
                    <tr key={r.userId} className="border-b border-surface-border/60 hover:bg-surface-subtle/50">
                      <td data-label="Employee" className="px-3 py-3 pl-4">
                        <p className="font-semibold text-gray-900">{r.fullName}</p>
                        <p className="text-xs text-gray-500">{r.employeeCode} · {r.categoryLabel}{r.isActive ? "" : " · inactive"}</p>
                      </td>
                      <td data-label="Salary" className="px-3 py-3 tabular-nums">{money(r.monthlySalary)}</td>
                      <td data-label="Days present" className="px-3 py-3 tabular-nums">{r.daysPresent}{r.absentDays ? <span className="text-xs text-status-danger"> · {r.absentDays} absent</span> : null}</td>
                      <td data-label="Paid days" className="px-3 py-3 tabular-nums">{r.paidDays}{r.markedDays ? <span className="text-xs text-gray-500"> · {r.markedDays} marked</span> : null}</td>
                      <td data-label="Amount" className="px-3 py-3 font-semibold tabular-nums">{money(r.amount)}</td>
                      <td data-label="Status" className="px-3 py-3"><Badge tone={STATUS[r.status].tone}>{STATUS[r.status].label}</Badge></td>
                      <td data-label="" className="px-3 py-3 text-right">
                        <Button size="sm" variant="secondary" onClick={() => setOpenUser(r.userId)}>{r.status === "PAID" ? "View payslip" : "Open payslip"}</Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {editPeriod && <PeriodModal month={data.month} period={data.period} onClose={() => setEditPeriod(false)} />}
          {openUser && <PayslipModal month={data.month} userId={openUser} onClose={() => setOpenUser(null)} />}
        </>
      )}
    </div>
  );
}
