import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import { useAuth } from "@/features/auth/useAuth";
import { money, useMarkPayslipSeen, useUnseenPayslips } from "@/features/payroll/api";

/** Shown once, the next time an employee opens the app after an admin has paid their salary. */
export function SalaryReceivedPopup() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const { data } = useUnseenPayslips();
  const seen = useMarkPayslipSeen();
  const slip = user ? data?.items[0] : undefined;
  if (!slip) return null;

  const close = () => seen.mutate(slip.id);
  return (
    <Modal
      open
      onClose={close}
      title="Salary received"
      footer={
        <>
          <Button variant="secondary" onClick={close}>Got it</Button>
          <Button onClick={() => { close(); navigate("/attendance?tab=payslips"); }}>View payslip</Button>
        </>
      }
    >
      <div className="flex flex-col items-center gap-2 py-2 text-center">
        <span className="flex h-14 w-14 items-center justify-center rounded-full bg-status-success/15 text-2xl" aria-hidden="true">✓</span>
        <p className="text-sm text-gray-600">Your salary for <b>{slip.monthLabel}</b> has been paid.</p>
        <p className="text-3xl font-extrabold tabular-nums text-heading">{money(slip.amount)}</p>
        <p className="text-xs text-gray-500">{slip.paidDays} of {slip.daysInMonth} days paid</p>
      </div>
    </Modal>
  );
}
