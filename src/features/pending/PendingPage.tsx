import { useMemo, useState } from "react";
import { PageHeader } from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Table, Td, Th, TableEmpty } from "@/components/ui/Table";
import { Skeleton } from "@/components/feedback/Skeleton";
import { ErrorState } from "@/components/feedback/ErrorState";
import { IconCheckCircle, IconDownload, IconRefresh, IconSearch } from "@/components/ui/icons";
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
  const [partner, setPartner] = useState("");
  const [dayOffset, setDayOffset] = useState(0);
  const [query, setQuery] = useState("");
  const { data, isLoading, isError, refetch, isFetching } = usePending(dayOffset, partner);

  const items = useMemo(() => {
    const q = query.trim().toLowerCase();
    return (data?.items ?? []).filter(
      (s) =>
        !q ||
        [s.name, s.externalCode, s.city, s.state, s.regionName, s.pocName, s.vendorName].some((f) =>
          (f ?? "").toLowerCase().includes(q),
        ),
    );
  }, [data, query]);

  const pct = data && data.liveStores ? Math.round((data.marked / data.liveStores) * 100) : 0;

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Pending entries"
        subtitle="Live stores that have no bottle count marked yet — call the store or vendor to chase them."
        action={
          <div className="flex flex-wrap gap-2">
            <Button variant="secondary" onClick={() => void refetch()} isLoading={isFetching}>
              <IconRefresh className="h-4 w-4" />
              Refresh
            </Button>
            <Button
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
              <IconDownload className="h-4 w-4" />
              Export CSV
            </Button>
          </div>
        }
      />

      <div className="flex flex-wrap items-center gap-2">
        {[{ slug: "", name: "All platforms" }, ...partners].map((p) => (
          <button
            key={p.slug}
            onClick={() => setPartner(p.slug)}
            className={`rounded-lg px-3 py-1.5 text-sm font-medium transition-colors ${
              partner === p.slug
                ? "bg-brand-500 text-white shadow-sm"
                : "bg-white text-gray-600 ring-1 ring-surface-border hover:bg-surface-subtle"
            }`}
          >
            {p.name}
          </button>
        ))}
        <div className="ml-auto flex gap-1 rounded-lg bg-surface-muted p-1">
          {[
            { v: 0, l: "Today" },
            { v: 1, l: "Yesterday" },
          ].map((d) => (
            <button
              key={d.v}
              onClick={() => setDayOffset(d.v)}
              className={`rounded-md px-3 py-1.5 text-sm font-medium transition-all ${
                dayOffset === d.v ? "bg-white text-brand-700 shadow-sm" : "text-gray-500 hover:text-gray-800"
              }`}
            >
              {d.l}
            </button>
          ))}
        </div>
      </div>

      {isLoading && <Skeleton className="h-64" />}
      {isError && <ErrorState message="Couldn't load pending entries." onRetry={() => refetch()} />}

      {data && (
        <>
          <div className="grid gap-4 sm:grid-cols-3">
            <div className="tile tile-warning rounded-xl border border-surface-border bg-white p-5 shadow-card">
              <p className="text-[11px] font-bold uppercase tracking-wider text-gray-500">Pending</p>
              <p className={`mt-1.5 text-[1.7rem] font-bold leading-none tabular-nums ${data.pending ? "text-status-warning" : "text-status-success"}`}>
                {data.pending}
              </p>
              <p className="mt-1 text-xs text-gray-500">{data.dateLabel} · {data.date}</p>
            </div>
            <div className="tile tile-brand rounded-xl border border-surface-border bg-white p-5 shadow-card">
              <p className="text-[11px] font-bold uppercase tracking-wider text-gray-500">Marked</p>
              <p className="mt-1.5 text-[1.7rem] font-bold leading-none tabular-nums text-ink-900">{data.marked}</p>
              <p className="mt-1 text-xs text-gray-500">of {data.liveStores} live stores</p>
            </div>
            <div className="tile tile-aqua rounded-xl border border-surface-border bg-white p-5 shadow-card">
              <p className="text-[11px] font-bold uppercase tracking-wider text-gray-500">Coverage</p>
              <p className="mt-1.5 text-[1.7rem] font-bold leading-none tabular-nums text-ink-900">{pct}%</p>
              <div className="mt-2.5 h-2 overflow-hidden rounded-full bg-surface-muted">
                <div
                  className={`h-full rounded-full ${pct >= 85 ? "bg-status-success" : pct >= 50 ? "bg-brand-500" : "bg-status-warning"}`}
                  style={{ width: `${pct}%` }}
                />
              </div>
            </div>
          </div>

          {data.pending === 0 ? (
            <div className="flex flex-col items-center gap-2 rounded-xl border border-surface-border bg-white px-6 py-14 text-center shadow-card">
              <span className="flex h-12 w-12 items-center justify-center rounded-full bg-status-success-soft text-status-success">
                <IconCheckCircle className="h-6 w-6" />
              </span>
              <p className="text-base font-bold text-ink-900">All caught up</p>
              <p className="text-sm text-gray-500">Every live store has an entry for {data.dateLabel.toLowerCase()}.</p>
            </div>
          ) : (
            <>
              <div className="relative w-full sm:w-80">
                <IconSearch className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" />
                <input
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="Search store, city, region or contact"
                  aria-label="Search pending stores"
                  className="h-10 w-full rounded-lg border border-surface-border bg-white pl-9 pr-3 text-sm shadow-sm outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20"
                />
              </div>
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
