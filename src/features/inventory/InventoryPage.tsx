import { SelectField } from "@/components/ui/Dropdown";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { PageHeader } from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Skeleton } from "@/components/feedback/Skeleton";
import { ErrorState } from "@/components/feedback/ErrorState";
import { EmptyState } from "@/components/feedback/EmptyState";
import { IconChevronDown, IconDownload, IconSearch } from "@/components/ui/icons";
import { usePartners } from "@/features/stores/useStores";
import { usePermission } from "@/hooks/usePermission";
import { downloadCsv } from "@/lib/csv";
import { apiRequest } from "@/services/api";
import { toInventory, type InventoryStore } from "@/types/inventory";

type Chip = "all" | "behind" | "uptodate" | "unmarked";
const CHIPS: { id: Chip; label: string }[] = [
  { id: "all", label: "All" },
  { id: "behind", label: "Behind" },
  { id: "uptodate", label: "Up to date" },
  { id: "unmarked", label: "Not marked today" },
];

function Phone({ value }: { value: string | null }) {
  if (!value) return <span className="text-gray-400">—</span>;
  return (
    <a href={`tel:${value}`} className="font-medium text-brand-600 hover:text-brand-700" onClick={(e) => e.stopPropagation()}>
      {value}
    </a>
  );
}

function PendingBadge({ days }: { days: number }) {
  if (days === 0) return <Badge tone="success">Up to date</Badge>;
  return <Badge tone={days >= 3 ? "danger" : "warning"}>{days} day{days > 1 ? "s" : ""} pending</Badge>;
}

function useInventory(partner: string) {
  return useQuery({
    queryKey: ["inventory", partner],
    queryFn: async () => toInventory(await apiRequest(`/orders/inventory${partner ? `?partner=${partner}` : ""}`)),
    staleTime: 30_000,
  });
}

export function InventoryPage() {
  const isAdmin = usePermission("orders.correct");
  const { data: partners = [] } = usePartners(isAdmin);
  const [partner, setPartner] = useState("");
  const [chip, setChip] = useState<Chip>("all");
  const [query, setQuery] = useState("");
  const [openGroups, setOpenGroups] = useState<Set<string>>(new Set());
  const { data, isLoading, isError, refetch } = useInventory(partner);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return (data?.items ?? []).filter((s) => {
      if (chip === "behind" && s.pendingDays === 0) return false;
      if (chip === "uptodate" && s.pendingDays > 0) return false;
      if (chip === "unmarked" && s.markedToday) return false;
      return (
        !q ||
        [s.name, s.externalCode, s.city, s.state, s.vendorName, s.pocName].some((f) => (f ?? "").toLowerCase().includes(q))
      );
    });
  }, [data, chip, query]);

  const groups = useMemo(() => {
    const map = new Map<string, InventoryStore[]>();
    filtered.forEach((s) => {
      const key = s.vendorName?.trim() || "No vendor";
      map.set(key, [...(map.get(key) ?? []), s]);
    });
    return [...map.entries()]
      .map(([vendor, stores]) => ({
        vendor,
        stores,
        number: stores.find((s) => s.vendorNumber)?.vendorNumber ?? null,
        behind: stores.filter((s) => s.pendingDays > 0).length,
        pendingDays: stores.reduce((n, s) => n + s.pendingDays, 0),
      }))
      .sort((a, b) => b.pendingDays - a.pendingDays || a.vendor.localeCompare(b.vendor));
  }, [filtered]);

  // few vendors → show everything; many (admin view) → start collapsed
  const autoOpen = groups.length <= 3 || query.trim().length > 0;
  const isOpen = (v: string) => autoOpen || openGroups.has(v);
  const toggle = (v: string) =>
    setOpenGroups((prev) => {
      const next = new Set(prev);
      if (next.has(v)) next.delete(v);
      else next.add(v);
      return next;
    });

  const s = data?.summary;

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Vendors"
        subtitle={`Stores grouped by vendor with contact details and pending days${data ? ` · ${data.monthLabel}` : ""}.`}
        action={
          <Button
            variant="secondary"
            disabled={!filtered.length}
            onClick={() =>
              downloadCsv(
                `inventory-${new Date().toISOString().slice(0, 10)}.csv`,
                ["Vendor", "Vendor number", "Store", "Code", "Platform", "City", "State", "POC", "POC number", "Start date", "Last entry", "Pending days", "Month bottles"],
                filtered.map((x) => [x.vendorName, x.vendorNumber, x.name, x.externalCode, x.platform, x.city, x.state, x.pocName, x.pocNumber, x.startDate, x.lastEntryDate, x.pendingDays, x.monthBottles]),
              )
            }
          >
            <IconDownload className="h-4 w-4" />
            Export CSV
          </Button>
        }
      />

      {s && (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {[
            { l: "Stores", v: s.stores, t: "brand" },
            { l: "Behind schedule", v: s.behind, t: "warning" },
            { l: "Marked today", v: `${s.markedToday} / ${s.stores}`, t: "success" },
            { l: "Total pending days", v: s.totalPendingDays, t: "aqua" },
          ].map((k) => (
            <div key={k.l} className={`tile tile-${k.t} rounded-xl border border-surface-border bg-white p-5 shadow-card`}>
              <p className="text-[11px] font-bold uppercase tracking-wider text-gray-500">{k.l}</p>
              <p className="mt-1.5 text-[1.7rem] font-bold leading-none tabular-nums text-ink-900">{k.v}</p>
            </div>
          ))}
        </div>
      )}

      <div className="flex flex-wrap items-center gap-2">
        {CHIPS.map((c) => (
          <button
            key={c.id}
            onClick={() => setChip(c.id)}
            className={`rounded-lg px-3 py-1.5 text-sm font-medium transition-colors ${
              chip === c.id ? "bg-brand-500 text-white shadow-sm" : "bg-white text-gray-600 ring-1 ring-surface-border hover:bg-surface-subtle"
            }`}
          >
            {c.label}
          </button>
        ))}
        {isAdmin && (
          <SelectField
            value={partner}
            onChange={(e) => setPartner(e.target.value)}
            aria-label="Platform"
            className="h-9 rounded-lg border border-surface-border bg-white px-3 text-sm shadow-sm"
          >
            <option value="">All platforms</option>
            {partners.map((p) => (
              <option key={p.slug} value={p.slug}>{p.name}</option>
            ))}
          </SelectField>
        )}
        <div className="relative ml-auto w-full sm:w-72">
          <IconSearch className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search store, vendor, city or POC"
            aria-label="Search inventory"
            className="h-10 w-full rounded-lg border border-surface-border bg-white pl-9 pr-3 text-sm shadow-sm outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20"
          />
        </div>
      </div>

      {isLoading && <Skeleton className="h-64" />}
      {isError && <ErrorState message="Couldn't load the inventory." onRetry={() => refetch()} />}
      {data && groups.length === 0 && (
        <EmptyState title="No stores match" description="Try a different filter or search." />
      )}

      <div className="flex flex-col gap-4">
        {groups.map((g) => (
          <section key={g.vendor} className="overflow-hidden rounded-xl border border-surface-border bg-white shadow-card">
            <button
              onClick={() => toggle(g.vendor)}
              aria-expanded={isOpen(g.vendor)}
              className="flex w-full flex-wrap items-center gap-x-4 gap-y-1 border-b border-surface-border/80 bg-surface-subtle px-5 py-3.5 text-left"
            >
              <span className="text-sm font-bold text-gray-900">{g.vendor}</span>
              <span className="text-xs text-gray-500">{g.stores.length} store{g.stores.length > 1 ? "s" : ""}</span>
              {g.number && (
                <span className="text-xs">
                  <Phone value={g.number} />
                </span>
              )}
              <span className="ml-auto flex items-center gap-3">
                {g.behind > 0 ? <Badge tone="warning">{g.behind} behind</Badge> : <Badge tone="success">All up to date</Badge>}
                <IconChevronDown className={`h-4 w-4 text-gray-400 transition-transform ${isOpen(g.vendor) ? "rotate-180" : ""}`} />
              </span>
            </button>

            {isOpen(g.vendor) && (
              <div className="stacked-table overflow-x-auto">
                <table className="w-full min-w-[720px] text-sm">
                  <thead>
                    <tr className="text-left text-[11px] font-bold uppercase tracking-wider text-gray-500">
                      <th className="px-5 py-2.5">Store</th>
                      <th className="px-3 py-2.5">Location</th>
                      <th className="px-3 py-2.5">POC</th>
                      <th className="px-3 py-2.5">Last entry</th>
                      <th className="px-3 py-2.5">Status</th>
                      <th className="px-3 py-2.5 text-right">Bottles (month)</th>
                      <th className="px-5 py-2.5 text-right">Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {g.stores.map((st) => (
                      <tr key={st.id} className="border-t border-surface-border/70">
                        <td className="px-5 py-3" data-label="Store">
                          <div className="font-medium text-gray-900">{st.name}</div>
                          <div className="text-xs text-gray-500">{st.externalCode}{st.platform ? ` · ${st.platform}` : ""}{st.startDate ? ` · since ${st.startDate}` : ""}</div>
                        </td>
                        <td className="px-3 py-3 text-gray-600" data-label="Location">{[st.city, st.state].filter(Boolean).join(", ") || "—"}</td>
                        <td className="px-3 py-3" data-label="POC">
                          <div>{st.pocName ?? "—"}</div>
                          <Phone value={st.pocNumber} />
                        </td>
                        <td className="px-3 py-3 text-gray-600" data-label="Last entry">{st.lastEntryDate ?? "—"}</td>
                        <td className="px-3 py-3" data-label="Status">
                          <div className="flex flex-wrap items-center gap-1.5">
                            <PendingBadge days={st.pendingDays} />
                            {st.markedToday && <Badge tone="info">Today ✓</Badge>}
                          </div>
                        </td>
                        <td className="px-3 py-3 text-right tabular-nums" data-label="Bottles (month)">{st.monthBottles}</td>
                        <td className="px-5 py-3 text-right" data-label="Action">
                          <div className="flex justify-end gap-3 text-sm font-semibold">
                            <Link to={`/orders?store=${st.id}`} className="text-brand-600 hover:text-brand-700">Mark →</Link>
                            <Link to={`/compliance?q=${encodeURIComponent(st.externalCode)}`} className="text-aqua-600 hover:text-aqua-700">Docs →</Link>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        ))}
      </div>
    </div>
  );
}
