import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { IconAlertTriangle } from "@/components/ui/icons";
import { BrandLogo } from "@/components/ui/BrandLogo";
import { apiRequest } from "@/services/api";
import { pushToast } from "@/lib/toast";

const MIN = 10; // keep in step with PASSWORD_MIN_LENGTH on the server

/** Forgot password: Employee ID -> a 6-digit code emailed to the address on the account -> a new password. */
export function ForgotPasswordPage() {
  const navigate = useNavigate();
  const [step, setStep] = useState<"id" | "code">("id");
  const [employeeCode, setEmployeeCode] = useState("");
  const [code, setCode] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [show, setShow] = useState(false);
  const [info, setInfo] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function sendCode(e?: FormEvent) {
    e?.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const r = await apiRequest<{ message: string; available: boolean }>("/auth/forgot-password", {
        method: "POST", silent: true, skipAuthRefresh: true, body: { employee_code: employeeCode.trim() },
      });
      setInfo(r.message);
      if (r.available) setStep("code");
      else setError(r.message);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't send the code. Try again.");
    } finally {
      setBusy(false);
    }
  }

  const rules = { length: next.trim().length >= MIN, mix: /[A-Za-z]/.test(next) && /\d/.test(next), match: next.length > 0 && next === confirm };
  const valid = /^\d{6}$/.test(code.trim()) && rules.length && rules.mix && rules.match;

  async function reset(e: FormEvent) {
    e.preventDefault();
    if (!valid) return;
    setError(null);
    setBusy(true);
    try {
      await apiRequest("/auth/reset-with-code", {
        method: "POST", silent: true, skipAuthRefresh: true,
        body: { employee_code: employeeCode.trim(), code: code.trim(), new_password: next },
      });
      pushToast("Password changed. Sign in with your new password.", "success");
      navigate("/login");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't change the password. Try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-surface px-4 py-10 sm:px-6">
      <div className="w-full max-w-sm animate-slide-up">
        <div className="mb-8 flex items-center gap-2.5">
          <BrandLogo height={40} />
          <span className="text-base font-semibold text-gray-900">Aquatrack</span>
        </div>
        <h1 className="text-2xl font-extrabold tracking-tight text-heading">Reset your password</h1>
        <p className="mt-1.5 text-sm text-gray-500">
          {step === "id"
            ? "Enter your Employee ID. We'll email a 6-digit code to the address saved on your account."
            : "Enter the code from your email and choose a new password."}
        </p>

        {step === "id" ? (
          <form onSubmit={sendCode} className="mt-6 flex flex-col gap-4" noValidate>
            <Input label="Employee ID" value={employeeCode} onChange={(e) => setEmployeeCode(e.target.value.toUpperCase())} autoComplete="username" required />
            {error && <Alert>{error}</Alert>}
            <Button type="submit" size="lg" fullWidth isLoading={busy} disabled={!employeeCode.trim()}>Email me a code</Button>
          </form>
        ) : (
          <form onSubmit={reset} className="mt-6 flex flex-col gap-4" noValidate>
            {info && <p className="rounded-xl bg-surface-subtle px-3.5 py-3 text-sm text-gray-600">{info}</p>}
            <Input label="6-digit code" value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, "").slice(0, 6))} inputMode="numeric" autoComplete="one-time-code" required />
            <Input
              label="New password" type={show ? "text" : "password"} value={next} onChange={(e) => setNext(e.target.value)} autoComplete="new-password"
              hint={`At least ${MIN} characters, with a letter and a number.`} required
              rightSlot={<button type="button" onClick={() => setShow((v) => !v)} className="rounded px-2 py-1 text-xs font-semibold text-gray-500 hover:text-gray-800">{show ? "Hide" : "Show"}</button>}
            />
            <Input label="Confirm new password" type={show ? "text" : "password"} value={confirm} onChange={(e) => setConfirm(e.target.value)} autoComplete="new-password" required
              error={confirm.length > 0 && !rules.match ? "The two passwords don't match." : undefined} />
            {error && <Alert>{error}</Alert>}
            <Button type="submit" size="lg" fullWidth isLoading={busy} disabled={!valid}>Change password</Button>
            <button type="button" className="text-sm font-semibold text-brand-600 hover:text-brand-700" onClick={() => void sendCode()} disabled={busy}>
              Send a new code
            </button>
          </form>
        )}

        <p className="mt-6 text-sm text-gray-500">
          <Link to="/login" className="font-semibold text-brand-600 hover:text-brand-700">Back to sign in</Link>
        </p>
      </div>
    </div>
  );
}

function Alert({ children }: { children: string }) {
  return (
    <div role="alert" className="flex items-start gap-2 rounded-xl border border-status-danger/25 bg-status-danger-soft px-3.5 py-3 text-sm text-status-danger">
      <IconAlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
      <span>{children}</span>
    </div>
  );
}
