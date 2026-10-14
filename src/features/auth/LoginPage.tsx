import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { IconAlertTriangle } from "@/components/ui/icons";
import { useAuth } from "@/features/auth/useAuth";
import { BrandLogo } from "@/components/ui/BrandLogo";

export function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
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
      await login(employeeCode, password);
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
          <BrandLogo tile height={44} />
          <span className="text-lg font-semibold tracking-tight">Aquatrack</span>
        </div>

        <div className="relative max-w-md">
          <span className="mb-5 inline-flex items-center gap-2 rounded-full bg-white/10 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.16em] text-aqua-200 ring-1 ring-white/10">
            <span className="h-1.5 w-1.5 rounded-full bg-status-success animate-pulse" /> Operations workspace
          </span>
          <h2 className="text-[2.2rem] font-extrabold leading-tight tracking-tight">
            Packaged drinking water logistics, perfected.
          </h2>
          <p className="mt-4 text-sm leading-relaxed text-white/70">
            Trusted by quick-commerce giants Blinkit and Zepto for over 14 years — keeping hundreds of dark stores
            stocked with pure water every single day.
          </p>

          <div className="mt-8 grid grid-cols-2 gap-3">
            <div className="rounded-2xl border border-white/10 bg-white/5 p-4 backdrop-blur-md">
              <p className="text-2xl font-extrabold text-white">99.9%</p>
              <p className="mt-0.5 text-xs text-white/60">On-time store fulfillment</p>
            </div>
            <div className="rounded-2xl border border-white/10 bg-white/5 p-4 backdrop-blur-md">
              <p className="text-2xl font-extrabold text-white">100k+</p>
              <p className="mt-0.5 text-xs text-white/60">Bottles tracked monthly</p>
            </div>
          </div>
        </div>

        <p className="relative text-xs text-white/60">© {new Date().getFullYear()} Veekay Aquatrack. All rights reserved.</p>
      </div>

      {/* Form panel */}
      <div className="flex items-center justify-center bg-surface px-4 py-10 sm:px-6">
        <div className="w-full max-w-sm animate-slide-up">
          <div className="mb-8 flex items-center gap-2.5 lg:hidden">
            <BrandLogo height={40} />
            <span className="text-base font-semibold text-gray-900">Aquatrack</span>
          </div>

          <h1 className="text-2xl font-extrabold tracking-tight text-heading">Welcome back</h1>
          <p className="mt-1.5 text-sm text-gray-500">Sign in to your Aquatrack operations command console.</p>

          <form onSubmit={handleSubmit} className="mt-6 flex flex-col gap-4" noValidate>
            <Input
              label="Employee ID"
              value={employeeCode}
              onChange={(e) => setEmployeeCode(e.target.value.toUpperCase())}
              autoComplete="username"
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
                  className="rounded px-2 py-1 text-xs font-semibold text-gray-500 hover:text-gray-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500"
                >
                  {showPassword ? "Hide" : "Show"}
                </button>
              }
            />

            {error && (
              <div
                role="alert"
                className="flex items-start gap-2 rounded-xl border border-status-danger/25 bg-status-danger-soft px-3.5 py-3 text-sm text-status-danger"
              >
                <IconAlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
                <span>{error}</span>
              </div>
            )}

            <Button type="submit" size="lg" fullWidth isLoading={isSubmitting} className="mt-1 shadow-glow">
              Sign in to Operations
            </Button>
          </form>

          {import.meta.env.DEV && (
            <div className="mt-8 rounded-2xl border border-surface-border bg-surface-subtle/80 p-4 shadow-xs">
              <div className="flex items-center justify-between mb-2.5">
                <p className="text-[11px] font-bold uppercase tracking-wider text-gray-500">Quick Demo Access</p>
                <span className="font-mono text-[11px] text-gray-400">Pass@123</span>
              </div>
              <div className="flex flex-col gap-2">
                {[
                  { code: "ADMIN001", role: "Super Admin", desc: "Full CRM control" },
                  { code: "EMP001", role: "Ops Lead", desc: "Blinkit · North" },
                  { code: "EMP002", role: "Field Rep", desc: "Zepto · Karnataka" },
                ].map((demo) => (
                  <button
                    key={demo.code}
                    type="button"
                    onClick={() => {
                      setEmployeeCode(demo.code);
                      setPassword("Pass@123");
                    }}
                    className="group flex items-center justify-between rounded-xl border border-surface-border bg-surface px-3 py-2 text-left text-xs transition-all hover:border-brand-500/50 hover:bg-brand-500/5 active:scale-[0.99]"
                  >
                    <div className="flex items-center gap-2">
                      <code className="rounded-md border border-brand-500/20 bg-brand-500/10 px-1.5 py-0.5 font-mono text-[11px] font-bold text-brand-600">
                        {demo.code}
                      </code>
                      <span className="font-semibold text-heading">{demo.role}</span>
                    </div>
                    <span className="text-gray-500 group-hover:text-brand-600 transition-colors">{demo.desc}</span>
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
