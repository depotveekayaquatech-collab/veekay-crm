import type { ComponentType, SVGProps } from "react";
import { Link } from "react-router-dom";
import { IconBox, IconCheckCircle, IconReceipt, IconStore, IconTicket } from "@/components/ui/icons";
import { daysAgo } from "@/lib/dates";
import { useVendorAuth } from "@/features/vendor/vendor-auth-context";
import { useBottles, useDailyOrders, useDocuments, useStores, useTickets } from "@/features/vendor/useVendorData";
import { ErrorNote, ListSkeleton, SectionTitle } from "@/features/vendor/parts";
import { fmtDate, niceName } from "@/features/vendor/format";

type Icon = ComponentType<SVGProps<SVGSVGElement>>;

function Tile({ to, label, value, icon: I, tone }: { to: string; label: string; value: number | undefined; icon: Icon; tone: "brand" | "warn" | "bad" | "ok" }) {
  const chip = { brand: "bg-brand-50 text-brand-600", warn: "bg-status-warning-soft text-status-warning", bad: "bg-status-danger-soft text-status-danger", ok: "bg-status-success-soft text-status-success" }[tone];
  return (
    <Link to={to} className="flex flex-col gap-3 rounded-2xl border border-surface-border bg-surface p-3.5 shadow-sm active:bg-surface-subtle">
      <span className={`flex h-9 w-9 items-center justify-center rounded-xl ${chip}`}><I className="h-[18px] w-[18px]" /></span>
      <span>
        <span className="block text-2xl font-bold leading-none text-heading">{value === undefined ? "–" : value.toLocaleString("en-IN")}</span>
        <span className="mt-1 block text-xs font-medium text-gray-500">{label}</span>
      </span>
    </Link>
  );
}

export function VendorHome() {
  const { account } = useVendorAuth();
  const isPoc = account?.kind === "poc";
  const stores = useStores();
  const week = useDailyOrders({ date_from: daysAgo(6), date_to: daysAgo(0) });
  const bottles = useBottles({ page_size: 1 });
  const open = useTickets({ status: "OPEN", page_size: 1 });
  const progress = useTickets({ status: "IN_PROGRESS", page_size: 1 });
  const bills = useDocuments({ kind: "bill", page_size: 100 });

  const today = daysAgo(0);
  const pending = (bills.data?.items ?? []).filter((d) => d.status === "PENDING");
  const overdue = pending.filter((d) => d.due_date && d.due_date <= today);
  const active = open.data && progress.data ? open.data.total + progress.data.total : undefined;
  const weekTotal = week.data?.reduce((n, d) => n + d.bottles, 0);
  const latest = week.data?.[0];

  return (
    <div className="flex flex-col gap-5">
      <section className="relative overflow-hidden rounded-2xl bg-ink-950 p-5 text-white">
        <div
          className="pointer-events-none absolute inset-0"
          style={{ backgroundImage: "radial-gradient(420px circle at 0% 0%, rgba(47,111,237,0.6), transparent 60%), radial-gradient(360px circle at 100% 100%, rgba(42,169,189,0.5), transparent 60%)" }}
        />
        <div className="relative">
          <span className="inline-flex rounded-full bg-white/10 px-2.5 py-1 text-[11px] font-semibold text-aqua-200 ring-1 ring-white/10">
            {isPoc ? "Store POC" : "Vendor"}
          </span>
          <h1 className="mt-3 text-xl font-bold leading-tight">Hello, {niceName(account?.full_name ?? "").split(" ")[0]}</h1>
          <p className="mt-0.5 text-sm text-white/70">{account?.store_count} store{account?.store_count === 1 ? "" : "s"} on your login</p>
          <div className="mt-5 flex items-end justify-between gap-3">
            <div>
              <p className="text-xs text-white/60">Bottles delivered, last 7 days</p>
              <p className="mt-0.5 text-4xl font-extrabold tracking-tight">{weekTotal === undefined ? "–" : weekTotal.toLocaleString("en-IN")}</p>
            </div>
            {latest && (
              <Link to="/vendor/orders" className="rounded-xl bg-white/10 px-3 py-2 text-right ring-1 ring-white/15">
                <span className="block text-[11px] text-white/60">{fmtDate(latest.order_date)}</span>
                <span className="block text-sm font-bold">{latest.bottles.toLocaleString("en-IN")}</span>
              </Link>
            )}
          </div>
        </div>
      </section>

      {isPoc ? (
        <div className="grid grid-cols-2 gap-3">
          <Link to="/vendor/deliveries/new" className="flex items-center justify-center gap-2 rounded-xl bg-brand-600 px-3 py-3.5 text-sm font-semibold text-white shadow-sm active:brightness-95">
            <IconCheckCircle className="h-4 w-4" /> Confirm delivery
          </Link>
          <Link to="/vendor/tickets/new" className="flex items-center justify-center gap-2 rounded-xl border border-brand-600 bg-surface px-3 py-3.5 text-sm font-semibold text-brand-700 shadow-sm active:bg-surface-subtle">
            <IconTicket className="h-4 w-4" /> Raise a ticket
          </Link>
        </div>
      ) : (
        <p className="rounded-xl bg-brand-50 px-3.5 py-3 text-sm text-brand-800">
          Your store POCs confirm deliveries and raise tickets. You can follow all of it here.
        </p>
      )}

      <div className="grid grid-cols-2 gap-3">
        <Tile to="/vendor/bottles" label="Bottles at your stores" value={bottles.data?.total} icon={IconBox} tone="brand" />
        <Tile to="/vendor/tickets" label="Active tickets" value={active} icon={IconTicket} tone={active ? "warn" : "ok"} />
        <Tile to="/vendor/documents?kind=bill" label="Bills to clear" value={bills.data ? pending.length : undefined} icon={IconReceipt} tone={overdue.length ? "bad" : pending.length ? "warn" : "ok"} />
        <Tile to="/vendor/stores" label="Your stores" value={account?.store_count} icon={IconStore} tone="brand" />
      </div>

      {overdue.length > 0 && (
        <Link to="/vendor/documents?kind=bill" className="rounded-xl border border-status-danger/25 bg-status-danger-soft px-3.5 py-3 text-sm font-medium text-status-danger">
          {overdue.length} bill{overdue.length === 1 ? " is" : "s are"} past the due date. Oldest was due {fmtDate(overdue.map((d) => d.due_date!).sort()[0])}.
        </Link>
      )}

      <section>
        <SectionTitle action={<Link to="/vendor/stores" className="text-xs font-semibold text-brand-600">See all</Link>}>Your stores</SectionTitle>
        {stores.isLoading ? (
          <ListSkeleton rows={3} />
        ) : stores.isError ? (
          <ErrorNote message="Couldn't load your stores." onRetry={() => stores.refetch()} />
        ) : (
          <div className="overflow-hidden rounded-2xl border border-surface-border bg-surface shadow-sm">
            {stores.data?.slice(0, 5).map((s) => (
              <Link key={s.id} to={`/vendor/orders?store=${s.id}`} className="flex items-center justify-between gap-3 border-b border-surface-border px-4 py-3 last:border-0 active:bg-surface-subtle">
                <span className="min-w-0">
                  <span className="block truncate text-sm font-semibold text-gray-900">{s.name}</span>
                  <span className="block truncate text-xs text-gray-500">{s.code}{s.city ? ` · ${s.city}` : ""}</span>
                </span>
                <span className="shrink-0 text-xs font-semibold text-gray-500">{bottles.data?.per_store[s.id] ?? 0} bottles</span>
              </Link>
            ))}
            {(stores.data?.length ?? 0) > 5 && (
              <Link to="/vendor/stores" className="block px-4 py-3 text-center text-sm font-semibold text-brand-600">
                View all {stores.data!.length} stores
              </Link>
            )}
          </div>
        )}
      </section>
    </div>
  );
}
