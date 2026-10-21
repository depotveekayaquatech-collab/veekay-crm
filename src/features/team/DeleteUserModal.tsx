import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Modal } from "@/components/ui/Modal";
import { useTeamMutations } from "@/features/team/useTeam";
import type { Employee } from "@/types/employee";

/** Developer only. Removes a deactivated user for good, so it asks for their Employee ID to be typed. */
export function DeleteUserModal({ employee, onClose }: { employee: Employee; onClose: () => void }) {
  const { deletePermanently } = useTeamMutations();
  const [code, setCode] = useState("");
  const matches = code.trim().toLowerCase() === employee.employeeCode.toLowerCase();

  return (
    <Modal
      open
      onClose={onClose}
      size="sm"
      title={`Delete ${employee.fullName} permanently?`}
      description="This cannot be undone from the app."
      footer={
        <>
          <Button variant="secondary" size="sm" onClick={onClose}>Cancel</Button>
          <Button
            size="sm"
            variant="danger"
            disabled={!matches || deletePermanently.isPending}
            onClick={() => deletePermanently.mutate({ id: employee.id, confirmCode: code.trim() }, { onSuccess: onClose })}
          >
            {deletePermanently.isPending ? "Deleting…" : "Delete permanently"}
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-4 text-sm text-gray-700">
        <ul className="list-disc space-y-1 pl-5">
          <li>Their login, phone and email are removed and they disappear from this page.</li>
          <li>Everything they did stays exactly as it is: orders, cash purchases, attendance, leave, salary, uploads and tickets keep their name and Employee ID.</li>
          <li>Their Employee ID can't be reused.</li>
        </ul>
        <Input label={`Type ${employee.employeeCode} to confirm`} value={code} onChange={(e) => setCode(e.target.value)} autoComplete="off" />
      </div>
    </Modal>
  );
}
