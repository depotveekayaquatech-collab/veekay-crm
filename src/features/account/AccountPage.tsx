import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { PageHeader } from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Skeleton } from "@/components/feedback/Skeleton";
import { ErrorState } from "@/components/feedback/ErrorState";
import { PasswordForm } from "@/features/auth/PasswordForm";
import { useAuth } from "@/features/auth/useAuth";
import { listSessions, revokeSession } from "@/services/auth";
import { describeDevice, timeAgo } from "@/lib/device";
import { useTheme } from "@/lib/theme";
import { pushToast } from "@/lib/toast";

function Card({ title, subtitle, children }: { title: string; subtitle?: string; children: React.ReactNode }) {
  return (
    <section className="rounded-xl border border-surface-border bg-surface shadow-card">
      <header className="border-b border-surface-border/80 px-5 py-4">
        <h3 className="text-sm font-bold text-gray-900">{title}</h3>
        {subtitle && <p className="mt-0.5 text-xs text-gray-500">{subtitle}</p>}
      </header>
      <div className="p-5">{children}</div>
    </section>
  );
}

function ThemeSwitch() {
  const [theme, setTheme] = useTheme();
  const dark = theme === "dark";
  return (
    <div className="flex items-center justify-between gap-4">
      <div>
        <p className="text-sm font-semibold text-gray-900">Dark theme</p>
        <p className="mt-0.5 text-xs text-gray-500">Easier on the eyes in low light. Saved on this device.</p>
      </div>
      <button
        type="button"
        role="switch"
        aria-checked={dark}
        aria-label="Dark theme"
        onClick={() => setTheme(dark ? "light" : "dark")}
        className={`relative inline-flex h-7 w-12 shrink-0 items-center rounded-full transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 ${
          dark ? "bg-brand-500" : "bg-gray-300"
        }`}
      >
        <span
          className={`inline-flex h-5 w-5 items-center justify-center rounded-full bg-white text-[11px] shadow transition-transform ${
            dark ? "translate-x-6" : "translate-x-1"
          }`}
          aria-hidden="true"
        >
          {dark ? "🌙" : "☀️"}
        </span>
      </button>
    </div>
  );
}

export function AccountPage() {
  const { user } = useAuth();
  const qc = useQueryClient();
  const sessions = useQuery({ queryKey: ["sessions"], queryFn: listSessions });
  const [busyId, setBusyId] = useState<string | null>(null);

  const revoke = useMutation({
    mutationFn: revokeSession,
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["sessions"] });
      pushToast("Device signed out.", "success");
    },
  });

  const others = (sessions.data ?? []).filter((s) => !s.current);

  async function signOutOthers() {
    setBusyId("all");
    try {
      await Promise.all(others.map((s) => revokeSession(s.id)));
      await qc.invalidateQueries({ queryKey: ["sessions"] });
      pushToast("Signed out of all other devices.", "success");
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <PageHeader title="My account" subtitle="Your sign-in details, password and the devices signed in to your account." />

      <div className="grid gap-6 xl:grid-cols-[1fr_1.2fr]">
        <div className="flex flex-col gap-6">
          <Card title="Profile">
            <dl className="grid gap-3 text-sm sm:grid-cols-2">
              {[
                ["Name", user?.fullName],
                ["Employee ID", user?.employeeCode],
                ["Platform", user?.platformLabel],
                ["Region", user?.regionName],
                ["Email", user?.email],
              ].map(([k, v]) => (
                <div key={k as string}>
                  <dt className="text-[11px] font-bold uppercase tracking-wider text-gray-500">{k}</dt>
                  <dd className="mt-0.5 font-medium text-gray-900">{v || "—"}</dd>
                </div>
              ))}
              <div className="sm:col-span-2">
                <dt className="text-[11px] font-bold uppercase tracking-wider text-gray-500">Roles</dt>
                <dd className="mt-1 flex flex-wrap gap-1.5">
                  {(user?.roles ?? []).map((r) => (
                    <Badge key={r} tone="info">{r.replace(/_/g, " ")}</Badge>
                  ))}
                </dd>
              </div>
            </dl>
          </Card>

          <Card title="Appearance" subtitle="Choose how the app looks for you.">
            <ThemeSwitch />
          </Card>

          <Card title="Change password" subtitle="You'll stay signed in here; every other device is signed out.">
            <PasswordForm />
          </Card>
        </div>

        <Card title="Devices signed in" subtitle="If you don't recognise one, sign it out and change your password.">
          {sessions.isLoading && <Skeleton className="h-40" />}
          {sessions.isError && <ErrorState message="Couldn't load your devices." onRetry={() => sessions.refetch()} />}
          {sessions.data && (
            <>
              <ul className="flex flex-col divide-y divide-surface-border">
                {sessions.data.map((s) => (
                  <li key={s.id} className="flex flex-wrap items-center gap-x-4 gap-y-2 py-3 first:pt-0 last:pb-0">
                    <div className="min-w-0 flex-1">
                      <p className="flex items-center gap-2 text-sm font-medium text-gray-900">
                        {describeDevice(s.userAgent)}
                        {s.current && <Badge tone="success">This device</Badge>}
                      </p>
                      <p className="text-xs text-gray-500">
                        {s.ip ? `${s.ip} · ` : ""}active {timeAgo(s.lastActiveAt)} · signed in {timeAgo(s.signedInAt)}
                      </p>
                    </div>
                    {!s.current && (
                      <Button
                        size="sm"
                        variant="secondary"
                        isLoading={revoke.isPending && revoke.variables === s.id}
                        onClick={() => revoke.mutate(s.id)}
                      >
                        Sign out
                      </Button>
                    )}
                  </li>
                ))}
              </ul>
              {others.length > 0 && (
                <Button className="mt-4" variant="secondary" isLoading={busyId === "all"} onClick={() => void signOutOthers()}>
                  Sign out of all other devices ({others.length})
                </Button>
              )}
            </>
          )}
        </Card>
      </div>
    </div>
  );
}
