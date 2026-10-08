import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { Badge } from "@/components/ui/Badge";
import { Skeleton } from "@/components/feedback/Skeleton";
import { ErrorState } from "@/components/feedback/ErrorState";
import { IconBox, IconCard, IconClipboard, IconPlus, IconReport, IconTicket } from "@/components/ui/icons";
import { ProgressBar, StatCard } from "@/features/orders/ui";
import { PriorityBadge, StatusBadge } from "@/features/tickets/parts";
import { timeAgo } from "@/lib/ticketTime";
import { apiRequest } from "@/services/api";
import { camelize } from "@/lib/camel";
import { TICKET_CODE, type TicketPriority, type TicketStatus } from "@/types/ticket";
import { useAuth } from "@/features/auth/useAuth";

interface Overview {
  platform: { slug: string | null; name: string };
  today: string;
  contact: string;
  sections: { entries: boolean; tickets: boolean };
  entries?: {
    stores: { live: number; pending: number; closed: number; total: number };
    today: { marked: number; of: number; percent: number; bottles: number; yesterdayEntries: number; yesterdayBottles: number };
    month: { entries: number; bottles: number; label: string };
    trend: { label: string; entries: number; bottles: number }[];
    regions: { region: string; stores: number; marked: number; bottles: number; percent: number }[];
    awaiting: { id: string; name: string; code: string; city: string | null; state: string | null; region: string | null }[];
    awaitingTotal: number;
  };
  tickets?: {
    open: number;
    inProgress: number;
    overdue: number;
    resolved30d: number;
    recent: { id: string; number: number; title: string; status: TicketStatus; priority: TicketPriority; store: string; createdAt: string; isOverdue: boolean }[];
  };
}

function usePartnerOverview() {
  return useQuery({
    queryKey: ["partner-overview"],
    queryFn: async () => camelize<Overview>(await apiRequest("/partner/overview")),
    refetchInterval: 120_000,
  });
}

function delta(now: number, before: number): { text: string; up: boolean } | null {
  if (!before) return null;
  const pct = Math.round(((now - before) / before) * 100);
  return { text: `${pct >= 0 ? "+" : ""}${pct}% vs yesterday`, up: pct >= 0 };
}

function TrendChart({ data }: { data: { label: string; entries: number; bottles: number }[] }) {
  const max = Math.max(1, ...data.map((d) => d.bottles));
  return (
    <section className="rounded-xl border border-surface-border bg-surface p-4 shadow-card sm:p-5">
      <div className="flex items-baseline justify-between">
        <h3 className="text-sm font-bold text-heading">Bottles delivered, last 14 days</h3>
        <span className="text-xs text-gray-400">today is still counting</span>
      </div>
      <div className="mt-4 flex h-40 items-end gap-1.5" role="img" aria-label="Bottles delivered per day">
        {data.map((d, i) => (
          <div key={d.label} className="flex h-full min-w-0 flex-1 flex-col justify-end gap-1" title={`${d.label}: ${d.bottles.toLocaleString()} bottles across ${d.entries} stores`}>
            <div className="flex flex-1 items-end">
              <div
                className={`w-full rounded-t ${i === data.length - 1 ? "bg-aqua-400" : "bg-brand-500"}`}
                style={{ height: `${(d.bottles / max) * 100}%`, minHeight: d.bottles ? 3 : 0 }}
              />
            </div>
            <span className="truncate text-center text-[9px] text-gray-400">{d.label.split(" ")[1]}</span>
          </div>
        ))}
      </div>
    </section>
  );
}

export function PartnerHomePage() {
  const { user, hasPermission } = useAuth();
  const { data, isLoading, isError, refetch } = usePartnerOverview();

  const links = [
    { to: "/orders", label: "Store entries", icon: IconClipboard, show: hasPermission("orders.view") },
    { to: "/inventory", label: "Vendors", icon: IconBox, show: hasPermission("orders.view") },
    { to: "/cards", label: "Store cards", icon: IconCard, show: hasPermission("orders.view") },
    { to: "/delivery-reports", label: "Delivery reports", icon: IconReport, show: hasPermission("reports.delivery") },
    { to: "/tickets", label: "Tickets", icon: IconTicket, show: hasPermission("tickets.view") },
  ].filter((l) => l.show);

  if (isLoading) {
    return (
      <div className="flex flex-col gap-6">
        <Skeleton className="h-36" />
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">{[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-28" />)}</div>
        <Skeleton className="h-64" />
      </div>
    );
  }
  if (isError || !data) return <ErrorState message="Couldn't load your overview." onRetry={() => refetch()} />;

  const e = data.entries;
  const t = data.tickets;
  const d = e ? delta(e.today.bottles, e.today.yesterdayBottles) : null;

  return (
    <div className="flex flex-col gap-6">
      <section className="relative overflow-hidden rounded-2xl bg-ink-950 p-6 text-white sm:p-8">
        <div
          className="pointer-events-none absolute inset-0"
          style={{
            backgroundImage:
              "radial-gradient(560px circle at 10% 0%, rgba(47,111,237,0.55), transparent 60%), radial-gradient(480px circle at 95% 100%, rgba(42,169,189,0.45), transparent 60%)",
          }}
        />
        <div className="relative flex flex-wrap items-end justify-between gap-5">
          <div>
            <span className="inline-flex items-center gap-2 rounded-full bg-white/10 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.16em] text-aqua-200 ring-1 ring-white/10">
              <span className="h-1.5 w-1.5 rounded-full bg-status-success-soft" /> {data.platform.name} partner portal
            </span>
            <h2 className="mt-4 text-[1.9rem] font-bold leading-tight tracking-tight">Welcome, {user?.fullName ?? data.contact}</h2>
            <p className="mt-1.5 max-w-xl text-sm text-white/70">
              Aquatrack's water deliveries to your {data.platform.name} stores — live numbers, vendor contacts and your open issues, in one place.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            {links.map((l) => {
              const Icon = l.icon;
              return (
                <Link key={l.to} to={l.to} className="flex items-center gap-2 rounded-lg bg-white/10 px-3.5 py-2 text-sm font-semibold text-white ring-1 ring-white/15 transition-colors hover:bg-white/20">
                  <Icon className="h-4 w-4" /> {l.label}
                </Link>
              );
            })}
            {hasPermission("tickets.create") && (
              <Link to="/tickets" className="flex items-center gap-2 rounded-lg bg-brand-500 px-3.5 py-2 text-sm font-semibold text-white transition-colors hover:bg-brand-400">
                <IconPlus className="h-4 w-4" /> Raise a ticket
              </Link>
            )}
          </div>
        </div>
      </section>

      {e && (
        <>
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <StatCard label="Live stores" value={e.stores.live} hint={`${e.stores.pending} starting soon · ${e.stores.closed} closed`} tone="brand" />
            <StatCard label="Entries today" value={`${e.today.marked} / ${e.today.of}`} tone="aqua" hint={`${e.today.percent}% of live stores`}>
              <ProgressBar percent={e.today.percent} className="mt-3" />
            </StatCard>
            <StatCard
              label="Bottles today"
              value={e.today.bottles.toLocaleString()}
              tone="success"
              hint={d ? <span className={d.up ? "text-status-success" : "text-status-warning"}>{d.text}</span> : `${e.today.yesterdayBottles.toLocaleString()} yesterday`}
            />
            <StatCard label={`Bottles in ${e.month.label.split(" ")[0]}`} value={e.month.bottles.toLocaleString()} hint={`${e.month.entries.toLocaleString()} store-days recorded`} tone="warning" valueClassName="text-heading" />
          </div>

          <div className="grid gap-6 xl:grid-cols-[3fr_2fr]">
            <TrendChart data={e.trend} />
            <section className="flex flex-col overflow-hidden rounded-xl border border-surface-border bg-surface shadow-card">
              <div className="flex items-center justify-between border-b border-surface-border px-4 py-3.5 sm:px-5">
                <h3 className="text-sm font-bold text-heading">Still to be marked today</h3>
                <Badge tone={e.awaitingTotal ? "warning" : "success"}>{e.awaitingTotal}</Badge>
              </div>
              {e.awaiting.length === 0 ? (
                <p className="px-5 py-10 text-center text-sm text-gray-500">Every live store has today's number.</p>
              ) : (
                <ul className="divide-y divide-surface-border">
                  {e.awaiting.map((s) => (
                    <li key={s.id} className="flex items-center justify-between gap-3 px-4 py-2.5 sm:px-5">
                      <span className="min-w-0">
                        <span className="block truncate text-sm font-medium text-gray-900">{s.name}</span>
                        <span className="block truncate text-xs text-gray-500">{[s.code, s.city, s.region].filter(Boolean).join(" · ")}</span>
                      </span>
                    </li>
                  ))}
                  {e.awaitingTotal > e.awaiting.length && (
                    <li className="px-5 py-2.5 text-center text-xs text-gray-500">+ {e.awaitingTotal - e.awaiting.length} more — see Store entries</li>
                  )}
                </ul>
              )}
            </section>
          </div>

          <section className="overflow-hidden rounded-xl border border-surface-border bg-surface shadow-card">
            <div className="border-b border-surface-border px-4 py-3.5 sm:px-5">
              <h3 className="text-sm font-bold text-heading">Regions today</h3>
              <p className="text-xs text-gray-500">Lowest completion first</p>
            </div>
            <div className="stacked-table overflow-x-auto">
              <table className="w-full min-w-[560px] text-sm">
                <thead>
                  <tr className="border-b border-surface-border bg-surface-subtle text-left text-xs font-semibold uppercase tracking-wide text-gray-500">
                    <th className="px-5 py-2.5">Region</th>
                    <th className="px-4 py-2.5">Stores marked</th>
                    <th className="px-4 py-2.5">Bottles</th>
                    <th className="w-56 px-4 py-2.5">Progress</th>
                  </tr>
                </thead>
                <tbody>
                  {e.regions.map((r) => (
                    <tr key={r.region} className="border-b border-surface-border last:border-0">
                      <td className="px-5 py-2.5 font-medium text-gray-900" data-label="Region">{r.region}</td>
                      <td className="px-4 py-2.5 tabular-nums" data-label="Stores marked">{r.marked} <span className="text-gray-400">/ {r.stores}</span></td>
                      <td className="px-4 py-2.5 font-semibold tabular-nums" data-label="Bottles">{r.bottles.toLocaleString()}</td>
                      <td className="px-4 py-2.5" data-label="Progress">
                        <div className="flex items-center gap-3">
                          <ProgressBar percent={r.percent} className="min-w-[6rem] flex-1" />
                          <span className="w-10 text-right text-xs font-semibold tabular-nums text-gray-600">{r.percent}%</span>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        </>
      )}

      {t && (
        <section className="overflow-hidden rounded-xl border border-surface-border bg-surface shadow-card">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-surface-border px-4 py-3.5 sm:px-5">
            <div>
              <h3 className="text-sm font-bold text-heading">Your tickets</h3>
              <p className="text-xs text-gray-500">
                {t.open} open · {t.inProgress} in progress · {t.resolved30d} resolved in the last 30 days
                {t.overdue > 0 && <span className="font-semibold text-status-danger"> · {t.overdue} overdue</span>}
              </p>
            </div>
            <Link to="/tickets" className="text-sm font-semibold text-brand-600 hover:text-brand-700">All tickets →</Link>
          </div>
          {t.recent.length === 0 ? (
            <p className="px-5 py-10 text-center text-sm text-gray-500">No tickets yet. If a delivery is late or short, raise one and we'll act on it.</p>
          ) : (
            <ul className="divide-y divide-surface-border">
              {t.recent.map((x) => (
                <li key={x.id} className="flex flex-wrap items-center gap-x-4 gap-y-1 px-4 py-3 sm:px-5">
                  <span className="w-16 shrink-0 text-xs font-semibold text-gray-400">{TICKET_CODE(x.number)}</span>
                  <span className="min-w-0 flex-1 basis-56">
                    <span className="block truncate text-sm font-medium text-gray-900">{x.title}</span>
                    <span className="block truncate text-xs text-gray-500">{x.store} · {timeAgo(x.createdAt)}</span>
                  </span>
                  <span className="flex items-center gap-1.5">
                    <PriorityBadge priority={x.priority} />
                    <StatusBadge status={x.status} />
                    {x.isOverdue && <Badge tone="danger">Overdue</Badge>}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </section>
      )}

      {!e && !t && (
        <p className="rounded-xl border border-dashed border-surface-border bg-surface px-6 py-12 text-center text-sm text-gray-500">
          Your account doesn't have anything switched on yet. Ask your Veekay contact to enable entries or tickets.
        </p>
      )}
    </div>
  );
}
