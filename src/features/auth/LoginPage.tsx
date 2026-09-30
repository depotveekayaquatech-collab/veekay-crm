import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { IconAlertTriangle } from "@/components/ui/icons";
import { useAuth } from "@/features/auth/useAuth";

export function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [organizationSlug, setOrganizationSlug] = useState("veekay");
  const [employeeCode, setEmployeeCode] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setIsSubmitting(true);
    try {
      await login(organizationSlug, employeeCode, password);
      navigate("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to sign in. Please try again.");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <div className="grid min-h-screen lg:grid-cols-2">
      {/* Brand panel — hidden on small screens */}
      <div className="relative hidden overflow-hidden bg-ink-950 p-12 text-white lg:flex lg:flex-col lg:justify-between">
        <div
          className="pointer-events-none absolute inset-0"
          style={{
            backgroundImage:
              "radial-gradient(600px circle at 15% 10%, rgba(47,111,237,0.55), transparent 60%), radial-gradient(520px circle at 90% 85%, rgba(42,169,189,0.45), transparent 60%), linear-gradient(rgba(255,255,255,0.04) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.04) 1px, transparent 1px)",
            backgroundSize: "auto, auto, 44px 44px, 44px 44px",
          }}
        />
        <div className="relative flex items-center gap-3">
          <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-brand-400 via-brand-600 to-aqua-500 text-lg font-extrabold shadow-glow ring-1 ring-white/20">
            V
          </span>
          <span className="text-lg font-semibold tracking-tight">Veekay Aquatech</span>
        </div>

        <div className="relative max-w-md">
          <span className="mb-5 inline-flex items-center gap-2 rounded-full bg-white/10 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.16em] text-aqua-200 ring-1 ring-white/10">
            <span className="h-1.5 w-1.5 rounded-full bg-status-success-soft" /> Operations workspace
          </span>
          <h2 className="text-[2.1rem] font-bold leading-tight tracking-tight">
            Packaged drinking water, delivered to Blinkit and Zepto stores.
          </h2>
          <p className="mt-5 text-sm leading-relaxed text-white/70">
            Trusted by quick-commerce partners for over 14 years — keeping shelves
            stocked with clean, reliable water, day in and day out.
          </p>
        </div>

        <p className="relative text-xs text-white/60">© {new Date().getFullYear()} Veekay Aquatech Pvt. Ltd.</p>
      </div>

      {/* Form panel */}
      <div className="flex items-center justify-center bg-white px-4 py-10 sm:px-6">
        <div className="w-full max-w-sm animate-slide-up">
          <div className="mb-8 flex items-center gap-2.5 lg:hidden">
            <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-brand-500 text-sm font-bold text-white">
              V
            </span>
            <span className="text-base font-semibold text-gray-900">Veekay Aquatech</span>
          </div>

          <h1 className="text-2xl font-bold text-ink-900">Welcome back</h1>
          <p className="mt-1.5 text-sm text-gray-500">Sign in to your workspace. Enter your credentials to continue.</p>

          <form onSubmit={handleSubmit} className="mt-6 flex flex-col gap-4" noValidate>
            <Input
              label="Organization"
              value={organizationSlug}
              onChange={(e) => setOrganizationSlug(e.target.value)}
              autoComplete="organization"
              required
            />
            <Input
              label="Employee ID"
              value={employeeCode}
              onChange={(e) => setEmployeeCode(e.target.value.toUpperCase())}
              autoComplete="username"
              placeholder="e.g. EMP001"
              required
            />
            <Input
              label="Password"
              type={showPassword ? "text" : "password"}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
              required
              rightSlot={
                <button
                  type="button"
                  onClick={() => setShowPassword((v) => !v)}
                  className="rounded px-2 py-1 text-xs font-medium text-gray-500 hover:text-gray-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500"
                >
                  {showPassword ? "Hide" : "Show"}
                </button>
              }
            />

            {error && (
              <div
                role="alert"
                className="flex items-start gap-2 rounded-md border border-status-danger/25 bg-status-danger-soft px-3 py-2.5 text-sm text-status-danger"
              >
                <IconAlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
                <span>{error}</span>
              </div>
            )}

            <Button type="submit" size="lg" fullWidth isLoading={isSubmitting} className="mt-1">
              Sign in
            </Button>
          </form>

          {import.meta.env.DEV && (
            <div className="mt-6 space-y-1 rounded-lg bg-surface-subtle px-3.5 py-3 text-xs text-gray-500 ring-1 ring-surface-border">
              <p className="font-medium text-gray-700">Demo access (password Pass@123)</p>
              <p><code className="text-gray-700">ADMIN001</code> — admin</p>
              <p><code className="text-gray-700">EMP001</code> — Blinkit, North region</p>
              <p><code className="text-gray-700">EMP002</code> — Zepto, Karnataka</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
