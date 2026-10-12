import { useState } from "react";
import { Link } from "react-router-dom";
import { EmptyState } from "@/components/feedback/EmptyState";
import { useBottles, useStores } from "@/features/vendor/useVendorData";
import { ErrorNote, ListSkeleton } from "@/features/vendor/parts";

export function VendorStores() {
  const stores = useStores();
  const bottles = useBottles({ page_size: 1 });
  const [needle, setNeedle] = useState("");
  const n = needle.trim().toLowerCase();
  const shown = (stores.data ?? []).filter((s) => !n || `${s.name} ${s.code} ${s.city ?? ""} ${s.state ?? ""}`.toLowerCase().includes(n));

  return (
    <div>
      <Link to="/vendor" className="text-sm font-semibold text-brand-600">← Home</Link>
      <h1 className="mt-2 text-xl font-bold text-heading">Your stores</h1>
      <p className="text-sm text-gray-500">{stores.data ? `${stores.data.length} stores` : "Loading…"}. Tap one to see its orders.</p>
      <input
        type="search"
        value={needle}
        onChange={(e) => setNeedle(e.target.value)}
        placeholder="Search by name, code or city"
        aria-label="Search stores"
        className="mt-4 h-11 w-full rounded-xl border border-surface-border bg-surface px-3.5 text-sm shadow-sm outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20"
      />
      <div className="mt-4">
        {stores.isLoading ? (
          <ListSkeleton />
        ) : stores.isError ? (
          <ErrorNote message={stores.error.message} onRetry={() => stores.refetch()} />
        ) : shown.length === 0 ? (
          <EmptyState title="No store matches" description="Try a different name, code or city." />
        ) : (
          <div className="overflow-hidden rounded-2xl border border-surface-border bg-surface shadow-sm">
            {shown.map((s) => (
              <Link key={s.id} to={`/vendor/orders?store=${s.id}`} className="flex items-center justify-between gap-3 border-b border-surface-border px-4 py-3 last:border-0 active:bg-surface-subtle">
                <span className="min-w-0">
                  <span className="block truncate text-sm font-semibold text-gray-900">{s.name}</span>
                  <span className="block truncate text-xs text-gray-500">
                    {s.platform ? `${s.platform[0].toUpperCase()}${s.platform.slice(1)} · ` : ""}{s.code}{s.city ? ` · ${s.city}` : ""}{s.state ? `, ${s.state}` : ""}
                  </span>
                </span>
                <span className="shrink-0 text-xs font-semibold text-gray-500">{bottles.data?.per_store[s.id] ?? 0} bottles</span>
              </Link>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
