import { distinctOptions } from "@/lib/options";
import { useMemo, useState } from "react";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Table, Td, Th, TableEmpty } from "@/components/ui/Table";
import { Skeleton } from "@/components/feedback/Skeleton";
import { ErrorState } from "@/components/feedback/ErrorState";
import { IconCheckCircle, IconDownload, IconRefresh } from "@/components/ui/icons";
import { ProgressBar, RegionFilter, SearchBox, SegmentedControl, StatCard } from "@/features/orders/ui";
import { usePartners } from "@/features/stores/useStores";
import { downloadCsv } from "@/lib/csv";
import { usePending } from "@/services/reports";

function Phone({ value }: { value: string | null }) {
  if (!value) return <span className="text-gray-400">—</span>;
  return (
    <a href={`tel:${value}`} className="font-medium text-brand-600 hover:text-brand-700">
      {value}
    </a>
  );
}

export function PendingPage() {
  const { data: partners = [] } = usePartners();
  const [pickedPartner, setPartner] = useState("");
  const [region, setRegion] = useState("");
  const partner = partners.some((p) => p.slug === pickedPartner) ? pickedPartner : (partners[0]?.slug ?? "");
  const [dayOffset, setDayOffset] = useState(0);
  const [query, setQuery] = useState("");
  const { data, isLoading, isError, refetch, isFetching } = usePending(dayOffset, partner);
  const regions = useMemo(() => distinctOptions(data?.items ?? [], (s) => (s.regionName ? { value: s.regionName, label: s.regionName } : null)), [data]);

  const items = useMemo(() => {
    const q = query.trim().toLowerCase();
    return (data?.items ?? []).filter(
      (s) =>
        (!region || s.regionName === region) &&
        (!q ||
        [s.name, s.externalCode, s.city, s.state, s.regionName, s.pocName, s.vendorName].some((f) =>
          (f ?? "").toLowerCase().includes(q),
        )),
    );
  }, [data, query, region]);

  const pct = data && data.liveStores ? Math.round((data.marked / data.liveStores) * 100) : 0;

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center gap-3">
        <SegmentedControl
          label="Platform"
          value={partner}
          onChange={(v) => {
            setPartner(v);
            setRegion("");
          }}
          options={partners.map((p) => ({ value: p.slug, label: p.name }))}
        />
        {regions.length > 1 && <RegionFilter value={region} onChange={setRegion} options={regions} className="sm:w-48 [&_label]:sr-only" />}
        <SegmentedControl
          label="Day"
          value={String(dayOffset)}
          onChange={(v) => setDayOffset(Number(v))}
          options={[
            { value: "0", label: "Today" },
            { value: "1", label: "Yesterday" },
          ]}
        />
        <div className="ml-auto flex flex-wrap gap-2">
          <Button size="sm" variant="secondary" onClick={() => void refetch()} isLoading={isFetching}>
            <IconRefresh className="h-3.5 w-3.5" />
            Refresh
          </Button>
          <Button
            size="sm"
            variant="secondary"
            disabled={!items.length}
            onClick={() =>
              data &&
              downloadCsv(
                `pending-${data.date}.csv`,
                ["Store", "Code", "Platform", "Region", "State", "City", "Vendor", "Vendor number", "POC", "POC number"],
                items.map((s) => [s.name, s.externalCode, s.platform, s.regionName, s.state, s.city, s.vendorName, s.vendorNumber, s.pocName, s.pocNumber]),
              )
            }
          >
            <IconDownload className="h-3.5 w-3.5" />
            Export CSV
          </Button>
        </div>
      </div>

      {isLoading && <Skeleton className="h-64" />}
      {isError && <ErrorState message="Couldn't load pending entries." onRetry={() => refetch()} />}

      {data && (
        <>
          <div className="grid gap-4 sm:grid-cols-3">
            <StatCard
              label="Pending"
              value={data.pending}
              hint={`${data.dateLabel} · ${data.date}`}
              tone="warning"
              valueClassName={data.pending ? "text-status-warning" : "text-status-success"}
            />
            <StatCard label="Marked" value={data.marked} hint={`of ${data.liveStores} live stores`} tone="brand" />
            <StatCard label="Coverage" value={`${pct}%`} tone="aqua">
              <ProgressBar percent={pct} className="mt-3" />
            </StatCard>
          </div>

          {data.pending === 0 ? (
            <div className="flex flex-col items-center gap-2 rounded-xl border border-surface-border bg-surface px-6 py-14 text-center shadow-card">
              <span className="flex h-12 w-12 items-center justify-center rounded-full bg-status-success-soft text-status-success">
                <IconCheckCircle className="h-6 w-6" />
              </span>
              <p className="text-base font-bold text-heading">All caught up</p>
              <p className="text-sm text-gray-500">Every live store has an entry for {data.dateLabel.toLowerCase()}.</p>
            </div>
          ) : (
            <>
              <SearchBox value={query} onChange={setQuery} placeholder="Search store, city, region or contact" className="w-full sm:w-80" />
              <div className="stacked-table">
                <Table>
                  <thead>
                    <tr>
                      <Th>Store</Th>
                      <Th>Platform</Th>
                      <Th>Location</Th>
                      <Th>Store contact</Th>
                      <Th>Vendor</Th>
                      <Th>Pending</Th>
                    </tr>
                  </thead>
                  <tbody>
                    {items.length === 0 && <TableEmpty colSpan={6}>No stores match your search.</TableEmpty>}
                    {items.map((s) => (
                      <tr key={s.id}>
                        <Td data-label="Store">
                          <div className="font-medium text-gray-900">{s.name}</div>
                          <div className="text-xs text-gray-500">{s.externalCode}</div>
                        </Td>
                        <Td data-label="Platform">
                          <Badge tone="info">{s.platform ?? "—"}</Badge>
                        </Td>
                        <Td data-label="Location">
                          <div>{[s.city, s.state].filter(Boolean).join(", ") || "—"}</div>
                          {s.regionName && <div className="text-xs text-gray-500">{s.regionName}</div>}
                        </Td>
                        <Td data-label="Store contact">
                          <div>{s.pocName ?? "—"}</div>
                          <Phone value={s.pocNumber} />
                        </Td>
                        <Td data-label="Vendor">
                          <div>{s.vendorName ?? "—"}</div>
                          <Phone value={s.vendorNumber} />
                        </Td>
                        <Td data-label="Pending">
                          <Badge tone={s.pendingDays >= 3 ? "danger" : s.pendingDays > 0 ? "warning" : "neutral"}>
                            {s.pendingDays > 0 ? `${s.pendingDays} day${s.pendingDays > 1 ? "s" : ""}` : "today only"}
                          </Badge>
                          <div className="mt-0.5 text-xs text-gray-500">{s.lastEntryDate ? `last ${s.lastEntryDate}` : "no entry this month"}</div>
                        </Td>
                      </tr>
                    ))}
                  </tbody>
                </Table>
              </div>
            </>
          )}
        </>
      )}
    </div>
  );
}
