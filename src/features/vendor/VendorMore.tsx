import { Link, useNavigate } from "react-router-dom";
import { EmptyState } from "@/components/feedback/EmptyState";
import { Button } from "@/components/ui/Button";
import { useBottles, useMarkRead, useNotifications } from "@/features/vendor/useVendorData";
import { useVendorAuth } from "@/features/vendor/vendor-auth-context";
import { Card, ErrorNote, ListSkeleton, PageNav, SectionTitle, StoreSelect } from "@/features/vendor/parts";
import { fmtDate, fmtDateTime, niceName } from "@/features/vendor/format";
import { useState } from "react";

export function VendorBottles() {
  const [store, setStore] = useState("");
  const [page, setPage] = useState(1);
  const q = useBottles({ store_id: store || undefined, page, page_size: 50 });
  return (
    <div>
      <Link to="/vendor" className="text-sm font-semibold text-brand-600">← Home</Link>
      <h1 className="mt-2 text-xl font-bold text-heading">Bottles at your stores</h1>
      <p className="text-sm text-gray-500">Oldest first, so you can see which have been there longest.</p>
      <div className="mt-4"><StoreSelect value={store} onChange={(v) => { setStore(v); setPage(1); }} allLabel="All my stores" /></div>
      <div className="mt-4">
        {q.isLoading ? (
          <ListSkeleton />
        ) : q.isError ? (
          <ErrorNote message={q.error.message} onRetry={() => q.refetch()} />
        ) : q.data!.items.length === 0 ? (
          <EmptyState title="No bottles at your stores" description="Bottles show here after they are scanned in." />
        ) : (
          <>
            <p className="mb-2 text-sm font-semibold text-gray-700">{q.data!.total} bottle{q.data!.total === 1 ? "" : "s"}</p>
            <div className="flex flex-col gap-1.5">
              {q.data!.items.map((b) => (
                <Card key={b.serial} className="flex items-center justify-between gap-3 !p-3">
                  <div className="min-w-0">
                    <p className="font-mono text-sm font-semibold text-gray-900">{b.serial}</p>
                    <p className="truncate text-xs text-gray-500">{b.store_name}</p>
                  </div>
                  <p className="shrink-0 text-xs text-gray-500">{b.last_in_at ? `since ${fmtDate(b.last_in_at)}` : ""}</p>
                </Card>
              ))}
            </div>
          </>
        )}
        {q.data && <PageNav page={page} pageSize={q.data.page_size} total={q.data.total} onPage={setPage} />}
      </div>
    </div>
  );
}

export function VendorAlerts() {
  const navigate = useNavigate();
  const q = useNotifications();
  const mark = useMarkRead();
  return (
    <div>
      <div className="flex items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold text-heading">Alerts</h1>
          <p className="text-sm text-gray-500">Updates on your tickets.</p>
        </div>
        {(q.data?.unread ?? 0) > 0 && <Button size="sm" variant="secondary" onClick={() => mark.mutate(undefined)}>Mark all read</Button>}
      </div>
      <div className="mt-4">
        {q.isLoading ? (
          <ListSkeleton />
        ) : q.isError ? (
          <ErrorNote message={q.error.message} onRetry={() => q.refetch()} />
        ) : q.data!.items.length === 0 ? (
          <EmptyState title="No alerts yet" description="You will see replies and status changes on your tickets here." />
        ) : (
          <div className="flex flex-col gap-2">
            {q.data!.items.map((n) => (
              <button
                key={n.id}
                type="button"
                onClick={() => {
                  if (!n.read) mark.mutate([n.id]);
                  if (n.kind === "ticket" && n.ref_id) navigate(`/vendor/tickets/${n.ref_id}`);
                }}
                className={`rounded-xl border p-3 text-left ${n.read ? "border-surface-border bg-surface" : "border-brand-200 bg-brand-50"}`}
              >
                <p className="text-sm font-semibold text-gray-900">{n.title}</p>
                <p className="mt-0.5 line-clamp-2 text-sm text-gray-600">{n.body}</p>
                <p className="mt-1 text-[11px] text-gray-500">{fmtDateTime(n.created_at)}</p>
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

export function VendorAccount() {
  const { account, logout } = useVendorAuth();
  const navigate = useNavigate();
  if (!account) return null;
  const rows: [string, string][] = [
    ["Name", niceName(account.full_name)],
    ["Type", account.kind === "vendor" ? "Vendor" : "Store POC"],
    ["Login", account.email],
    ["Phone", account.phone ?? "–"],
    ["Platforms", account.platforms.map((p) => p[0].toUpperCase() + p.slice(1)).join(", ") || "–"],
    ["Stores", String(account.store_count)],
  ];
  return (
    <div>
      <h1 className="text-xl font-bold text-heading">Account</h1>
      <Card className="mt-4 !p-0">
        <dl className="divide-y divide-surface-border">
          {rows.map(([k, v]) => (
            <div key={k} className="flex justify-between gap-4 px-4 py-3 text-sm">
              <dt className="text-gray-500">{k}</dt>
              <dd className="truncate text-right font-medium text-gray-900">{v}</dd>
            </div>
          ))}
        </dl>
      </Card>
      <SectionTitle>More</SectionTitle>
      <div className="flex flex-col gap-2">
        <Link to="/vendor/deliveries" className="rounded-xl border border-surface-border bg-surface px-4 py-3 text-sm font-semibold text-gray-900">Delivery history</Link>
        <Link to="/vendor/bottles" className="rounded-xl border border-surface-border bg-surface px-4 py-3 text-sm font-semibold text-gray-900">Bottles at my stores</Link>
      </div>
      <Button variant="secondary" fullWidth className="mt-6" onClick={() => logout().then(() => navigate("/vendor/login", { replace: true }))}>
        Sign out
      </Button>
    </div>
  );
}
