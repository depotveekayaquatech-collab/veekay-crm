import { useMemo, useState } from "react";
import { SearchBox } from "@/features/orders/ui";
import { useDebounced } from "@/hooks/useDebounced";
import { PageHeader } from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Pagination } from "@/components/ui/Pagination";
import { Select } from "@/components/ui/Select";
import { Table, Td, Th, TableEmpty } from "@/components/ui/Table";
import { Skeleton } from "@/components/feedback/Skeleton";
import { ErrorState } from "@/components/feedback/ErrorState";
import { IconDownload, IconPlus } from "@/components/ui/icons";
import { downloadCsv } from "@/lib/csv";
import { usePermission } from "@/hooks/usePermission";
import { useAllRegions } from "@/features/regions/useRegions";
import { StoreFormModal } from "@/features/stores/StoreFormModal";
import { useAllStores } from "@/features/stores/useAllStores";
import { usePartners, useStores } from "@/features/stores/useStores";
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
  const [q, setQ] = useState("");
  const search = useDebounced(q.trim());

  const canManage = usePermission("stores.manage");
  const { data: allRegions = [] } = useAllRegions();
  const { data: everyStore = [] } = useAllStores();
  // With a platform picked, only offer the regions that actually have stores of that platform.
  const regions = useMemo(() => {
    if (!partner) return allRegions;
    const ids = new Set(everyStore.filter((s) => s.partnerSlug === partner && s.regionId).map((s) => s.regionId));
    return allRegions.filter((r) => ids.has(r.id));
  }, [allRegions, everyStore, partner]);
  const { data: partners = [] } = usePartners();
  const { data, isLoading, isError, refetch } = useStores(page, {
    regionId: regionId || undefined,
    partner: partner || undefined,
    storeStatus: storeStatus || undefined,
    search: search || undefined,
  });

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Stores"
        subtitle="Partner outlets your teams deliver water to. Live stores are the ones in work."
        action={
          <div className="flex flex-wrap gap-2">
            <Button
              variant="secondary"
              disabled={!data?.items.length}
              onClick={() =>
                data &&
                downloadCsv(
                  `stores-${new Date().toISOString().slice(0, 10)}.csv`,
                  ["Store", "Code", "Partner", "Region", "State", "City", "Start date", "Status", "POC", "POC number"],
                  data.items.map((x) => [
                    x.name, x.externalCode, x.partnerName, x.regionName, x.state, x.city, x.startDate, x.status, x.pocName, x.pocNumber,
                  ]),
                )
              }
            >
              <IconDownload className="h-4 w-4" />
              Export CSV
            </Button>
            {canManage && (
              <Button onClick={() => setEditing(null)}>
                <IconPlus className="h-4 w-4" />
                Add store
              </Button>
            )}
          </div>
        }
      />

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
                : "bg-surface text-gray-600 ring-1 ring-surface-border hover:bg-surface-subtle"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      <SearchBox
        hotkey
        className="sm:max-w-xl"
        value={q}
        onChange={(v) => {
          setQ(v);
          setPage(1);
        }}
        placeholder="Search store name, outlet ID, city, state, vendor or POC"
      />

      <div className="grid gap-3 sm:max-w-lg sm:grid-cols-2">
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
                <Th>Start date</Th>
                <Th>Status</Th>
                {canManage && <Th className="w-20 text-right">Actions</Th>}
              </tr>
            </thead>
            <tbody>
              {data.items.length === 0 && (
                <TableEmpty colSpan={canManage ? 8 : 7}>
                  No stores match{search ? ` “${search}”` : " these filters"}.
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
                </TableEmpty>
              )}
              {data.items.map((store) => (
                <tr key={store.id}>
                  <Td className="font-medium text-gray-900">{store.name}</Td>
                  <Td>{store.externalCode}</Td>
                  <Td>{store.partnerName}</Td>
                  <Td>{store.regionName ?? "—"}</Td>
                  <Td>{store.state ?? "—"}</Td>
                  <Td>{store.startDate ?? <span className="text-gray-400">—</span>}</Td>
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
