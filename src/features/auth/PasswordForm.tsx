import { useState, type FormEvent } from "react";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { IconAlertTriangle, IconCheckCircle } from "@/components/ui/icons";
import { pushToast } from "@/lib/toast";
import { useAuth } from "@/features/auth/useAuth";

const MIN = 10; // keep in step with PASSWORD_MIN_LENGTH on the server

function Rule({ ok, children }: { ok: boolean; children: string }) {
  return (
    <li className={`flex items-center gap-2 text-xs ${ok ? "text-status-success" : "text-gray-500"}`}>
      <span className={`flex h-4 w-4 items-center justify-center rounded-full text-[10px] font-bold ${ok ? "bg-status-success-soft" : "bg-surface-muted"}`}>
        {ok ? "✓" : "·"}
      </span>
      {children}
    </li>
  );
}

/** Change-own-password form. The server re-checks every rule; this just gives instant feedback. */
export function PasswordForm({ forced = false, onDone }: { forced?: boolean; onDone?: () => void }) {
  const { user, changePassword } = useAuth();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [show, setShow] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const code = (user?.employeeCode ?? "").toLowerCase();
  const rules = {
    length: next.length >= MIN,
    mix: /[A-Za-z]/.test(next) && /\d/.test(next),
    noCode: code.length < 3 || !next.toLowerCase().includes(code),
    differs: next.length > 0 && next !== current,
    match: confirm.length > 0 && confirm === next,
  };
  const valid = rules.length && rules.mix && rules.noCode && rules.differs && rules.match && current.length > 0;

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!valid) return;
    setError(null);
    setBusy(true);
    try {
      await changePassword(current, next);
      pushToast("Password changed. Your other devices were signed out.", "success");
      setCurrent("");
      setNext("");
      setConfirm("");
      onDone?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't change the password.");
    } finally {
      setBusy(false);
    }
  }

  const toggle = (
    <button
      type="button"
      onClick={() => setShow((v) => !v)}
      className="rounded px-2 py-1 text-xs font-medium text-gray-500 hover:text-gray-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500"
    >
      {show ? "Hide" : "Show"}
    </button>
  );
  const type = show ? "text" : "password";

  return (
    <form onSubmit={submit} className="flex flex-col gap-4" noValidate>
      <Input
        label={forced ? "Temporary password" : "Current password"}
        type={type}
        value={current}
        onChange={(e) => setCurrent(e.target.value)}
        autoComplete="current-password"
        required
        rightSlot={toggle}
      />
      <Input label="New password" type={type} value={next} onChange={(e) => setNext(e.target.value)} autoComplete="new-password" required />
      <Input
        label="Confirm new password"
        type={type}
        value={confirm}
        onChange={(e) => setConfirm(e.target.value)}
        autoComplete="new-password"
        required
        error={confirm.length > 0 && !rules.match ? "Passwords don't match." : undefined}
      />

      <ul className="grid gap-1.5 rounded-lg bg-surface-subtle px-3.5 py-3 sm:grid-cols-2">
        <Rule ok={rules.length}>{`At least ${MIN} characters`}</Rule>
        <Rule ok={rules.mix}>A letter and a number</Rule>
        <Rule ok={rules.noCode}>Doesn&apos;t contain your Employee ID</Rule>
        <Rule ok={rules.differs}>Different from the current password</Rule>
      </ul>

      {error && (
        <div role="alert" className="flex items-start gap-2 rounded-lg border border-status-danger/25 bg-status-danger-soft px-3 py-2.5 text-sm text-status-danger">
          <IconAlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      <div className="flex items-center gap-3">
        <Button type="submit" isLoading={busy} disabled={!valid}>
          <IconCheckCircle className="h-4 w-4" />
          {forced ? "Set password & continue" : "Change password"}
        </Button>
        <p className="text-xs text-gray-500">All your other devices will be signed out.</p>
      </div>
    </form>
  );
}
