import { useState } from "react";
import { PageHeader } from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Pagination } from "@/components/ui/Pagination";
import { Select } from "@/components/ui/Select";
import { Table, Td, Th, TableEmpty } from "@/components/ui/Table";
import { Skeleton } from "@/components/feedback/Skeleton";
import { ErrorState } from "@/components/feedback/ErrorState";
import { IconPlus } from "@/components/ui/icons";
import { usePermission } from "@/hooks/usePermission";
import { useAllRegions } from "@/features/regions/useRegions";
import { StoreFormModal } from "@/features/stores/StoreFormModal";
import { usePartners, useStores, useStoreMutations } from "@/features/stores/useStores";
import type { Store } from "@/types/store";

const STATUS_TABS = [
  { value: "LIVE", label: "Live" },
  { value: "PENDING", label: "Pending" },
  { value: "CLOSE", label: "Closed" },
  { value: "", label: "All" },
];

export function StoresPage() {
  const [page, setPage] = useState(1);
  const [regionId, setRegionId] = useState("");
  const [partner, setPartner] = useState("");
  const [storeStatus, setStoreStatus] = useState("LIVE");
  const [editing, setEditing] = useState<Store | null | undefined>(undefined);

  const canManage = usePermission("stores.manage");
  const { data: regions = [] } = useAllRegions();
  const { data: partners = [] } = usePartners();
  const { sync } = useStoreMutations();
  const { data, isLoading, isError, refetch } = useStores(page, {
    regionId: regionId || undefined,
    partner: partner || undefined,
    storeStatus: storeStatus || undefined,
  });

  const syncWarnings = sync.data?.flatMap((r) => r.warnings) ?? [];

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Stores"
        subtitle="Partner outlets your teams deliver water to. Live stores are the ones in work."
        action={
          canManage && (
            <div className="flex flex-wrap gap-2">
              <Button variant="secondary" onClick={() => sync.mutate(undefined)} isLoading={sync.isPending}>
                Sync from Sheet
              </Button>
              <Button onClick={() => setEditing(null)}>
                <IconPlus className="h-4 w-4" />
                Add store
              </Button>
            </div>
          )
        }
      />

      {sync.data && (
        <div className="rounded-lg border border-surface-border bg-white p-4 text-sm shadow-card">
          <p className="font-medium text-gray-900">Last sync</p>
          <ul className="mt-1 flex flex-wrap gap-x-6 gap-y-1 text-gray-600">
            {sync.data.map((r) => (
              <li key={r.platform}>
                <span className="font-medium capitalize">{r.platform}</span>: {r.created} added,{" "}
                {r.updated} updated, {r.unchanged} unchanged ({r.rowsRead} rows)
              </li>
            ))}
          </ul>
          {syncWarnings.length > 0 && (
            <details className="mt-2">
              <summary className="cursor-pointer text-xs font-medium text-status-warning">
                {syncWarnings.length} warning{syncWarnings.length > 1 ? "s" : ""}
              </summary>
              <ul className="mt-1 max-h-40 list-disc overflow-auto pl-5 text-xs text-gray-500">
                {syncWarnings.map((w, i) => (
                  <li key={i}>{w}</li>
                ))}
              </ul>
            </details>
          )}
        </div>
      )}

      {/* status = "what's in work" vs the rest */}
      <div className="flex flex-wrap items-center gap-1.5">
        {STATUS_TABS.map((t) => (
          <button
            key={t.value}
            onClick={() => {
              setStoreStatus(t.value);
              setPage(1);
            }}
            className={`rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
              storeStatus === t.value
                ? "bg-brand-500 text-white"
                : "bg-white text-gray-600 ring-1 ring-surface-border hover:bg-surface-subtle"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      <div className="grid gap-3 sm:max-w-lg sm:grid-cols-2">
        <Select
          label="Partner"
          value={partner}
          onChange={(e) => {
            setPartner(e.target.value);
            setPage(1);
          }}
          placeholder="All partners"
          options={partners.map((p) => ({ value: p.slug, label: p.name }))}
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
        />
      </div>

      {isLoading && <Skeleton className="h-64" />}
      {isError && <ErrorState message="Couldn't load stores." onRetry={() => refetch()} />}

      {data && (
        <>
          <Table>
            <thead>
              <tr>
                <Th>Store</Th>
                <Th>Code</Th>
                <Th>Partner</Th>
                <Th>Region</Th>
                <Th>State</Th>
                <Th>Status</Th>
                {canManage && <Th className="w-20 text-right">Actions</Th>}
              </tr>
            </thead>
            <tbody>
              {data.items.length === 0 && (
                <TableEmpty colSpan={canManage ? 7 : 6}>No stores match these filters.</TableEmpty>
              )}
              {data.items.map((store) => (
                <tr key={store.id}>
                  <Td className="font-medium text-gray-900">{store.name}</Td>
                  <Td>{store.externalCode}</Td>
                  <Td>{store.partnerName}</Td>
                  <Td>{store.regionName ?? "—"}</Td>
                  <Td>{store.state ?? "—"}</Td>
                  <Td>
                    <Badge
                      tone={
                        store.status === "LIVE" ? "success" : store.status === "PENDING" ? "warning" : "neutral"
                      }
                    >
                      {store.status}
                    </Badge>
                  </Td>
                  {canManage && (
                    <Td className="text-right">
                      <button
                        className="text-sm font-medium text-brand-600 hover:text-brand-700"
                        onClick={() => setEditing(store)}
                      >
                        Edit
                      </button>
                    </Td>
                  )}
                </tr>
              ))}
            </tbody>
          </Table>
          <Pagination page={data.page} pageSize={data.pageSize} total={data.total} onPageChange={setPage} />
        </>
      )}

      {editing !== undefined && (
        <StoreFormModal key={editing?.id ?? "new"} onClose={() => setEditing(undefined)} store={editing ?? null} />
      )}
    </div>
  );
}
