import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { Modal } from "@/components/ui/Modal";
import { Button } from "@/components/ui/Button";
import { apiRequest } from "@/services/api";
import { pushToast } from "@/lib/toast";
import type { Employee } from "@/types/employee";

/** Admin: issue a one-time temporary password. It is shown once and never stored readable. */
export function ResetPasswordModal({ employee, onClose }: { employee: Employee; onClose: () => void }) {
  const [copied, setCopied] = useState(false);
  const reset = useMutation({
    mutationFn: () => apiRequest<{ temp_password: string }>(`/employees/${employee.id}/reset-password`, { method: "POST" }),
  });
  const pw = reset.data?.temp_password;

  async function copy() {
    if (!pw) return;
    try {
      await navigator.clipboard.writeText(pw);
      setCopied(true);
      pushToast("Copied.", "success");
    } catch {
      pushToast("Couldn't copy — select the password and copy it manually.", "error");
    }
  }

  return (
    <Modal
      open
      onClose={onClose}
      title={pw ? "Temporary password" : "Reset password?"}
      description={`${employee.fullName} · ${employee.employeeCode}`}
      size="sm"
      footer={
        pw ? (
          <Button onClick={onClose}>Done</Button>
        ) : (
          <>
            <Button variant="secondary" onClick={onClose}>Cancel</Button>
            <Button variant="danger" isLoading={reset.isPending} onClick={() => reset.mutate()}>Reset password</Button>
          </>
        )
      }
    >
      {pw ? (
        <div className="flex flex-col gap-3">
          <div className="flex items-center gap-2 rounded-lg border border-surface-border bg-surface-subtle px-3 py-3">
            <code className="min-w-0 flex-1 select-all break-all text-base font-bold tracking-wide text-heading">{pw}</code>
            <Button size="sm" variant="secondary" onClick={() => void copy()}>{copied ? "Copied" : "Copy"}</Button>
          </div>
          <p className="rounded-lg bg-status-warning-soft px-3 py-2.5 text-xs text-status-warning">
            This is shown only now. Share it with {employee.fullName.split(" ")[0]} privately — they&apos;ll be asked to choose their own
            password at their next sign-in.
          </p>
        </div>
      ) : (
        <div className="flex flex-col gap-2 text-sm text-gray-600">
          <p>This will:</p>
          <ul className="list-disc space-y-1 pl-5">
            <li>sign {employee.fullName.split(" ")[0]} out of every device,</li>
            <li>unlock the account if it was locked,</li>
            <li>give them a one-time temporary password they must replace.</li>
          </ul>
          {reset.error && <p className="text-status-danger">{reset.error instanceof Error ? reset.error.message : "Couldn't reset."}</p>}
        </div>
      )}
    </Modal>
  );
}
