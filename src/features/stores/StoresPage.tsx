import { useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { SearchBox } from "@/features/orders/ui";
import { StoreTable } from "@/features/stores/StoreTable";
import { usePersistentState } from "@/hooks/usePersistentState";
import { useDebounced } from "@/hooks/useDebounced";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/Button";
import { Pagination } from "@/components/ui/Pagination";
import { Select } from "@/components/ui/Select";
import { Skeleton } from "@/components/feedback/Skeleton";
import { ErrorState } from "@/components/feedback/ErrorState";
import { IconDownload, IconPlus } from "@/components/ui/icons";
import { downloadCsv } from "@/lib/csv";
import { usePermission } from "@/hooks/usePermission";
import { useAllRegions } from "@/features/regions/useRegions";
import { StoreCard } from "@/features/stores/StoreCard";
import { StoreDetailsModal } from "@/features/stores/StoreDetailsModal";
import { DeleteClosedStoresModal } from "@/features/stores/DeleteClosedStoresModal";
import { DuplicateStores, useDuplicateStores } from "@/features/stores/DuplicateStores";
import { StoreFormModal } from "@/features/stores/StoreFormModal";
import { useAllStores } from "@/features/stores/useAllStores";
import { usePartners, useStoreMutations, useStores } from "@/features/stores/useStores";
import type { Store } from "@/types/store";

const STATUS_TABS = [
  { value: "LIVE", label: "Live" },
  { value: "PENDING", label: "Pending" },
  { value: "CLOSE", label: "Closed" },
  { value: "", label: "All" },
];

export function StoresPage() {
  // A link such as /stores?search=ZPT000360 (from the command palette) opens the list already narrowed to that store, across every status.
  const [params] = useSearchParams();
  const [layout, setLayout] = usePersistentState<"cards" | "table">("stores.layout", "cards");      // cards stay the default; the table is a choice, remembered
  const linked = (params.get("search") ?? "").slice(0, 80);
  const [page, setPage] = useState(1);
  const [regionId, setRegionId] = useState("");
  const [partner, setPartner] = useState("");
  const [storeStatus, setStoreStatus] = useState(linked ? "" : "LIVE");
  const [editing, setEditing] = useState<Store | null | undefined>(undefined);
  const [q, setQ] = useState(linked);
  const [viewing, setViewing] = useState<Store | null>(null);
  const search = useDebounced(q.trim());

  const canManage = usePermission("stores.manage");
  const canMerge = usePermission("stores.manage");          // store managers may merge duplicates (it moves all records first)
  const [view, setView] = useState<"stores" | "duplicates">("stores");
  const [deletingClosed, setDeletingClosed] = useState(false);
  const duplicates = useDuplicateStores();
  const duplicateGroups = duplicates.data?.totalGroups ?? 0;
  const { data: allRegions = [] } = useAllRegions();
  const { data: everyStore = [] } = useAllStores();
  // With a platform picked, only offer the regions that actually have stores of that platform.
  const regions = useMemo(() => {
    if (!partner) return allRegions;
    const ids = new Set(everyStore.filter((s) => s.partnerSlug === partner && s.regionId).map((s) => s.regionId));
    return allRegions.filter((r) => ids.has(r.id));
  }, [allRegions, everyStore, partner]);
  const { data: partners = [] } = usePartners();
  const { close } = useStoreMutations();
  const { data, isLoading, isError, refetch } = useStores(page, {
    regionId: regionId || undefined,
    partner: partner || undefined,
    storeStatus: storeStatus || undefined,
    search: search || undefined,
  });

  if (view === "duplicates") {
    return (
      <div className="flex flex-col gap-6">
        <PageHeader
          title="Duplicate stores"
          subtitle="A store's name is its identity, so a name or Outlet ID that appears twice needs fixing."
          action={<Button variant="secondary" onClick={() => setView("stores")}>Back to stores</Button>}
        />
        <DuplicateStores canMerge={canMerge} onEdit={(s) => setEditing(s)} />
        {editing !== undefined && <StoreFormModal key={editing?.id ?? "new"} onClose={() => setEditing(undefined)} store={editing ?? null} />}
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Stores"
        subtitle="Partner outlets your teams deliver water to. Live stores are the ones in work."
        action={
          <div className="flex flex-wrap gap-2">
            <Button variant="secondary" onClick={() => setView("duplicates")}>
              Duplicates
              {duplicateGroups > 0 && (
                <span className="ml-1.5 rounded-full bg-status-warning px-1.5 text-[11px] font-bold text-white">{duplicateGroups}</span>
              )}
            </Button>
            <Button
              variant="secondary"
              disabled={!data?.items.length}
              onClick={() =>
                data &&
                downloadCsv(
                  `stores-${new Date().toISOString().slice(0, 10)}.csv`,
                  ["Store", "CRM code", "Code", "Partner", "Region", "State", "City", "Start date", "Status", "POC", "POC number"],
                  data.items.map((x) => [
                    x.name, x.crmCode, x.externalCode, x.partnerName, x.regionName, x.state, x.city, x.startDate, x.status, x.pocName, x.pocNumber,
                  ]),
                )
              }
            >
              <IconDownload className="h-4 w-4" />
              Export CSV
            </Button>
            {canManage && (
              <Button variant="secondary" onClick={() => setDeletingClosed(true)}>
                Delete closed stores
              </Button>
            )}
            {canManage && (
              <Button onClick={() => setEditing(null)}>
                <IconPlus className="h-4 w-4" />
                Add store
              </Button>
            )}
          </div>
        }
      />

      {/* Control Toolbar */}
      <div className="flex flex-col gap-3 rounded-2xl border border-surface-border bg-surface p-4 shadow-card">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex flex-wrap items-center gap-1 rounded-xl bg-surface-subtle p-1 ring-1 ring-surface-border">
            {STATUS_TABS.map((t) => {
              const active = storeStatus === t.value;
              return (
                <button
                  key={t.value}
                  onClick={() => {
                    setStoreStatus(t.value);
                    setPage(1);
                  }}
                  className={`rounded-lg px-3.5 py-1.5 text-xs font-semibold transition-[color,background-color,border-color,box-shadow,opacity,transform] ${
                    active
                      ? "bg-brand-600 text-white"
                      : "text-gray-600 hover:bg-surface hover:text-gray-900"
                  }`}
                >
                  {t.label}
                </button>
              );
            })}
          </div>

          <div className="flex items-center gap-3">
            {(partner || regionId || q || storeStatus !== "LIVE") && (
              <button
                onClick={() => {
                  setPartner("");
                  setRegionId("");
                  setQ("");
                  setStoreStatus("LIVE");
                  setPage(1);
                }}
                className="text-xs font-semibold text-brand-600 hover:text-brand-700"
              >
                Clear filters
              </button>
            )}
            <div role="group" aria-label="Layout" className="hidden items-center gap-0.5 rounded-lg border border-surface-border p-0.5 md:flex">
              {(["cards", "table"] as const).map((v) => (
                <button key={v} type="button" aria-pressed={layout === v} onClick={() => setLayout(v)}
                  className={`min-h-7 rounded-md px-2.5 text-xs font-semibold transition-colors ${layout === v ? "bg-brand-600 text-white" : "text-gray-600 hover:bg-surface-subtle"}`}>
                  {v === "cards" ? "Cards" : "Table"}
                </button>
              ))}
            </div>
            <span className="text-xs font-medium text-gray-500">
              {data ? `${data.total} store${data.total === 1 ? "" : "s"}` : ""}
            </span>
          </div>
        </div>

        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <div className="lg:col-span-2">
            <SearchBox
              hotkey
              value={q}
              onChange={(v) => {
                setQ(v);
                setPage(1);
              }}
              placeholder="Search store name, CRM code, outlet ID, city, POC…"
              className="w-full"
            />
          </div>
          <Select
            label="Partner"
            value={partner}
            onChange={(e) => {
              setPartner(e.target.value);
              setRegionId("");
              setPage(1);
            }}
            placeholder="All partners"
            options={partners.map((p) => ({ value: p.slug, label: p.name }))}
            className="[&_label]:sr-only"
          />
          <Select
            label="Region"
            value={regionId}
            onChange={(e) => {
              setRegionId(e.target.value);
              setPage(1);
            }}
            placeholder="All regions"
            options={regions.map((r) => ({ value: r.id, label: r.name }))}
            className="[&_label]:sr-only"
          />
        </div>
      </div>

      {isLoading && <Skeleton className="h-64" />}
      {isError && <ErrorState message="Couldn't load stores." onRetry={() => refetch()} />}

      {data && (
        <>
          {data.items.length === 0 ? (
            <div className="rounded-2xl border border-dashed border-surface-border bg-surface p-10 text-center text-sm text-gray-500">
              No stores match{search ? ` \u201c${search}\u201d` : " these filters"}.
              {search && storeStatus && (
                <button
                  className="ml-2 font-medium text-brand-600 hover:text-brand-700"
                  onClick={() => {
                    setStoreStatus("");
                    setPage(1);
                  }}
                >
                  Search all statuses
                </button>
              )}
            </div>
          ) : (
            <>
              {layout === "table" && (
                <div className="hidden md:block">
                  <StoreTable
                    stores={data.items}
                    canManage={canManage}
                    onView={(store) => setViewing(store)}
                    onEdit={(store) => setEditing(store)}
                    onClose={(store) => {
                      if (window.confirm(`Close ${store.name}? Its order history is kept and you can set it Live again later.`)) close.mutate(store.id);
                    }}
                  />
                </div>
              )}
            <div className={`grid gap-4 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4 ${layout === "table" ? "md:hidden" : ""}`}>
              {data.items.map((store) => (
                <StoreCard
                  key={store.id}
                  store={store}
                  canManage={canManage}
                  onView={() => setViewing(store)}
                  onEdit={() => setEditing(store)}
                  onClose={() => {
                    if (window.confirm(`Close ${store.name}? Its order history is kept and you can set it Live again later.`)) close.mutate(store.id);
                  }}
                />
              ))}
            </div>
            </>
          )}
          <Pagination page={data.page} pageSize={data.pageSize} total={data.total} onPageChange={setPage} />
        </>
      )}


      {viewing && (
        <StoreDetailsModal
          store={viewing}
          onClose={() => setViewing(null)}
          onEdit={canManage ? () => { setEditing(viewing); setViewing(null); } : undefined}
        />
      )}
      {editing !== undefined && (
        <StoreFormModal key={editing?.id ?? "new"} onClose={() => setEditing(undefined)} store={editing ?? null} />
      )}
      {deletingClosed && <DeleteClosedStoresModal onClose={() => setDeletingClosed(false)} />}
    </div>
  );
}
