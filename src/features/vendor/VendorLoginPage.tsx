import { useState, type FormEvent } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { FullPageLoader } from "@/components/feedback/Skeleton";
import { BrandLogo } from "@/components/ui/BrandLogo";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { IconAlertTriangle } from "@/components/ui/icons";
import { useVendorAuth } from "@/features/vendor/vendor-auth-context";

const EMAIL_OK = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export function VendorLoginPage() {
  const { account, isLoading, login } = useVendorAuth();
  const navigate = useNavigate();
  const from = (useLocation().state as { from?: string } | null)?.from;
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [show, setShow] = useState(false);
  const [touched, setTouched] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (isLoading) return <FullPageLoader />;
  const target = from?.startsWith("/vendor") ? from : "/vendor";
  if (account) return <Navigate to={target} replace />;

  const emailError = touched && !EMAIL_OK.test(email.trim()) ? "Enter your full login, like name@supplier.com" : undefined;
  const passwordError = touched && !password ? "Enter your password" : undefined;

  async function submit(e: FormEvent) {
    e.preventDefault();
    setTouched(true);
    setError(null);
    if (!EMAIL_OK.test(email.trim()) || !password) return;
    setBusy(true);
    try {
      await login(email, password);
      navigate(target, { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't sign in. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto flex min-h-dvh max-w-md flex-col bg-ink-950">
      <div className="relative overflow-hidden px-7 pb-16 pt-[max(2.5rem,env(safe-area-inset-top))] text-white">
        <div
          className="pointer-events-none absolute inset-0"
          style={{ backgroundImage: "radial-gradient(360px circle at 0% 0%, rgba(47,111,237,0.55), transparent 60%), radial-gradient(320px circle at 100% 100%, rgba(42,169,189,0.45), transparent 60%)" }}
        />
        <div className="relative">
          <span className="inline-flex rounded-2xl bg-white px-3.5 py-2.5 shadow-sm"><BrandLogo height={34} /></span>
          <h1 className="mt-7 text-[1.9rem] font-extrabold leading-tight tracking-tight">Veekay Partner</h1>
          <p className="mt-1.5 text-[15px] leading-relaxed text-white/70">Orders, deliveries and tickets for your stores, in one place.</p>
        </div>
      </div>

      <div className="relative -mt-7 flex flex-1 flex-col rounded-t-[28px] bg-surface px-6 pb-[max(1.5rem,env(safe-area-inset-bottom))] pt-7">
        <h2 className="text-[1.35rem] font-bold text-heading">Sign in</h2>
        <p className="mb-5 mt-1 text-sm text-gray-500">Use the login your Veekay contact gave you.</p>

        <form onSubmit={submit} className="flex flex-col gap-4" noValidate>
          <Input
            label="Login (email)"
            type="email"
            inputMode="email"
            autoCapitalize="none"
            autoCorrect="off"
            autoComplete="username"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="name@supplier.com"
            error={emailError}
            disabled={busy}
          />
          <Input
            label="Password"
            type={show ? "text" : "password"}
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="Your password"
            error={passwordError}
            disabled={busy}
            rightSlot={
              <button type="button" onClick={() => setShow((v) => !v)} aria-label={show ? "Hide password" : "Show password"} className="rounded px-2 py-1 text-xs font-semibold text-gray-500">
                {show ? "Hide" : "Show"}
              </button>
            }
          />
          {error && (
            <div role="alert" className="flex items-start gap-2 rounded-xl bg-status-danger-soft px-3 py-2.5 text-sm text-status-danger">
              <IconAlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
              <span>{error}</span>
            </div>
          )}
          <Button type="submit" size="lg" fullWidth isLoading={busy} className="!h-[52px] !rounded-xl !text-base">Sign in</Button>
        </form>

        <div className="mt-7 rounded-xl bg-surface-subtle px-4 py-3.5 text-[13px] leading-relaxed text-gray-600">
          <p className="font-semibold text-gray-800">Forgot your password or can't sign in?</p>
          <p className="mt-0.5">Your Veekay contact can reset it for you.</p>
        </div>
      </div>
    </div>
  );
}
