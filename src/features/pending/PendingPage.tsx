import { distinctOptions } from "@/lib/options";
import { useMemo, useState } from "react";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Skeleton } from "@/components/feedback/Skeleton";
import { ErrorState } from "@/components/feedback/ErrorState";
import { IconAlertTriangle, IconCheckCircle, IconDownload, IconMapPin, IconRefresh, IconStore } from "@/components/ui/icons";
import { FilterChip, ProgressBar, ProgressRing, RegionFilter, SearchBox, SegmentedControl, StatCard } from "@/features/orders/ui";
import { usePartners } from "@/features/stores/useStores";
import { usePersistentState } from "@/hooks/usePersistentState";
import { downloadCsv } from "@/lib/csv";
import { pushToast } from "@/lib/toast";
import { usePending } from "@/services/reports";
import type { PendingStore } from "@/types/report";

type Urgency = "all" | "late" | "recent" | "today";

const urgencyOf = (s: PendingStore): Exclude<Urgency, "all"> => (s.pendingDays >= 3 ? "late" : s.pendingDays > 0 ? "recent" : "today");

function CallButton({ label, name, phone }: { label: string; name: string | null; phone: string | null }) {
  if (!phone && !name) return null;
  return (
    <div className="flex items-center justify-between gap-2 rounded-lg bg-surface-subtle px-3 py-2">
      <div className="min-w-0">
        <p className="text-[10px] font-bold uppercase tracking-wider text-gray-400">{label}</p>
        <p className="truncate text-sm font-semibold text-gray-900">{name ?? "—"}</p>
      </div>
      {phone && (
        <a
          href={`tel:${phone}`}
          aria-label={`Call ${name ?? label} on ${phone}`}
          className="shrink-0 rounded-lg bg-brand-500/10 px-2.5 py-1.5 text-xs font-bold tabular-nums text-brand-600 transition-colors hover:bg-brand-500 hover:text-white"
        >
          {phone}
        </a>
      )}
    </div>
  );
}

function StoreCard({ s }: { s: PendingStore }) {
  const level = urgencyOf(s);
  const bar = { late: "bg-status-danger", recent: "bg-status-warning", today: "bg-gray-300" }[level];
  const place = [s.city, s.state].filter(Boolean).join(", ");
  return (
    <li className="relative overflow-hidden rounded-2xl border border-surface-border bg-surface p-4 shadow-card transition-shadow hover:shadow-md">
      <span aria-hidden="true" className={`absolute inset-y-0 left-0 w-1 ${bar}`} />
      <div className="flex items-start justify-between gap-3 pl-1.5">
        <div className="min-w-0">
          <p className="flex items-center gap-1.5 truncate text-sm font-bold text-gray-900">
            <IconStore className="h-4 w-4 shrink-0 text-gray-400" aria-hidden="true" />
            <span className="truncate">{s.name}</span>
          </p>
          <p className="mt-0.5 flex flex-wrap items-center gap-x-2 text-xs text-gray-500">
            <span className="font-medium text-gray-600">{s.externalCode}</span>
            {place && (
              <span className="flex items-center gap-1">
                <IconMapPin className="h-3 w-3" aria-hidden="true" />
                {place}
              </span>
            )}
            {s.regionName && <span>{s.regionName}</span>}
          </p>
        </div>
        <div className="shrink-0 text-right">
          <Badge tone={level === "late" ? "danger" : level === "recent" ? "warning" : "neutral"}>
            {s.pendingDays > 0 ? `${s.pendingDays} day${s.pendingDays > 1 ? "s" : ""}` : "today only"}
          </Badge>
          <p className="mt-1 text-[11px] text-gray-400">{s.lastEntryDate ? `last ${s.lastEntryDate}` : "no entry this month"}</p>
        </div>
      </div>
      <div className="mt-3 grid gap-2 pl-1.5 sm:grid-cols-2">
        <CallButton label="Store contact" name={s.pocName} phone={s.pocNumber} />
        <CallButton label="Vendor" name={s.vendorName} phone={s.vendorNumber} />
      </div>
    </li>
  );
}

export function PendingPage() {
  const { data: partners = [] } = usePartners();
  const [pickedPartner, setPartner] = usePersistentState<string>("orders.platform", "");
  const [region, setRegion] = useState("");
  const partner = partners.some((p) => p.slug === pickedPartner) ? pickedPartner : (partners[0]?.slug ?? "");
  const [dayOffset, setDayOffset] = useState(0);
  const [query, setQuery] = useState("");
  const [urgency, setUrgency] = useState<Urgency>("all");
  const { data, isLoading, isError, refetch, isFetching } = usePending(dayOffset, partner);
  const regions = useMemo(() => distinctOptions(data?.items ?? [], (s) => (s.regionName ? { value: s.regionName, label: s.regionName } : null)), [data]);

  const scoped = useMemo(() => {
    const q = query.trim().toLowerCase();
    return (data?.items ?? []).filter(
      (s) =>
        (!region || s.regionName === region) &&
        (!q || [s.name, s.externalCode, s.city, s.state, s.regionName, s.pocName, s.vendorName].some((f) => (f ?? "").toLowerCase().includes(q))),
    );
  }, [data, query, region]);

  const counts = useMemo(
    () => ({ late: scoped.filter((s) => urgencyOf(s) === "late").length, recent: scoped.filter((s) => urgencyOf(s) === "recent").length, today: scoped.filter((s) => urgencyOf(s) === "today").length }),
    [scoped],
  );
  // Longest-waiting stores first — they're the ones worth a phone call.
  const items = useMemo(
    () => scoped.filter((s) => urgency === "all" || urgencyOf(s) === urgency).sort((a, b) => b.pendingDays - a.pendingDays || a.name.localeCompare(b.name)),
    [scoped, urgency],
  );

  const pct = data && data.liveStores ? Math.round((data.marked / data.liveStores) * 100) : 0;

  async function copyList() {
    if (!data) return;
    const text = [
      `Pending entries · ${data.dateLabel} (${data.date})`,
      ...items.map((s) => `• ${s.name} (${s.externalCode})${s.city ? `, ${s.city}` : ""} — ${s.pendingDays > 0 ? `${s.pendingDays}d pending` : "today"}${s.pocNumber ? ` — ${s.pocNumber}` : ""}`),
    ].join("\n");
    try {
      await navigator.clipboard.writeText(text);
      pushToast(`Copied ${items.length} store${items.length === 1 ? "" : "s"} to the clipboard.`, "success");
    } catch {
      pushToast("Couldn't copy — your browser blocked clipboard access.", "error");
    }
  }

  return (
    <div className="flex flex-col gap-5">
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
            <IconRefresh className="h-3.5 w-3.5" aria-hidden="true" />
            Refresh
          </Button>
          <Button size="sm" variant="secondary" disabled={!items.length} onClick={() => void copyList()}>
            Copy list
          </Button>
          <Button
            size="sm"
            variant="secondary"
            disabled={!items.length}
            onClick={() =>
              data &&
              downloadCsv(
                `pending-${data.date}.csv`,
                ["Store", "Code", "Platform", "Region", "State", "City", "Vendor", "Vendor number", "POC", "POC number", "Days pending"],
                items.map((s) => [s.name, s.externalCode, s.platform, s.regionName, s.state, s.city, s.vendorName, s.vendorNumber, s.pocName, s.pocNumber, s.pendingDays]),
              )
            }
          >
            <IconDownload className="h-3.5 w-3.5" aria-hidden="true" />
            Export CSV
          </Button>
        </div>
      </div>

      {isLoading && <Skeleton className="h-64 !rounded-2xl" />}
      {isError && <ErrorState message="Couldn't load pending entries." onRetry={() => refetch()} />}

      {data && (
        <>
          <div className="grid gap-4 sm:grid-cols-3">
            <StatCard label="Pending" value={data.pending} hint={`${data.dateLabel} · ${data.date}`} tone={data.pending ? "warning" : "success"} icon={IconAlertTriangle} />
            <StatCard label="Marked" value={data.marked} hint={`of ${data.liveStores} live stores`} tone="brand" icon={IconCheckCircle} />
            <StatCard label="Coverage" value={`${pct}%`} tone="aqua">
              <ProgressBar percent={pct} className="mt-3" />
            </StatCard>
          </div>

          {data.pending === 0 ? (
            <div className="flex flex-col items-center gap-3 rounded-2xl border border-surface-border bg-surface px-6 py-14 text-center shadow-card">
              <ProgressRing percent={100} size={96} label="✓" />
              <p className="text-base font-extrabold text-heading">All caught up</p>
              <p className="text-sm text-gray-500">Every live store has an entry for {data.dateLabel.toLowerCase()}.</p>
            </div>
          ) : (
            <>
              <div className="flex flex-wrap items-center gap-3">
                <SearchBox hotkey value={query} onChange={setQuery} placeholder="Search store, city, region or contact" className="w-full sm:w-80" />
                <div className="flex flex-wrap gap-1.5">
                  <FilterChip active={urgency === "all"} onClick={() => setUrgency("all")} count={scoped.length}>All</FilterChip>
                  <FilterChip active={urgency === "late"} onClick={() => setUrgency("late")} count={counts.late}>3+ days</FilterChip>
                  <FilterChip active={urgency === "recent"} onClick={() => setUrgency("recent")} count={counts.recent}>1–2 days</FilterChip>
                  <FilterChip active={urgency === "today"} onClick={() => setUrgency("today")} count={counts.today}>Today only</FilterChip>
                </div>
              </div>

              {items.length === 0 ? (
                <p className="rounded-2xl border border-dashed border-surface-border bg-surface px-6 py-12 text-center text-sm text-gray-500">No stores match your filters.</p>
              ) : (
                <ul className="grid gap-4 md:grid-cols-2 2xl:grid-cols-3">
                  {items.map((s) => (
                    <StoreCard key={s.id} s={s} />
                  ))}
                </ul>
              )}
            </>
          )}
        </>
      )}
    </div>
  );
}
