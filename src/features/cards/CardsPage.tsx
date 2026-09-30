import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/Button";
import { Skeleton } from "@/components/feedback/Skeleton";
import { ErrorState } from "@/components/feedback/ErrorState";
import { EmptyState } from "@/components/feedback/EmptyState";
import { IconSearch } from "@/components/ui/icons";
import { usePartners } from "@/features/stores/useStores";
import { usePermission } from "@/hooks/usePermission";
import { apiBlob, apiRequest } from "@/services/api";
import { pushToast } from "@/lib/toast";
import { monthLabel, recentMonths } from "@/lib/months";

interface Vendor {
  vendor: string;
  stores: number;
  number: string | null;
}

async function openPdf(params: URLSearchParams): Promise<void> {
  const win = window.open("", "_blank"); // opened synchronously so popup blockers allow it
  try {
    const blob = await apiBlob(`/cards/pdf?${params}`);
    const url = URL.createObjectURL(blob);
    if (win) win.location.href = url;
    else window.location.href = url;
    setTimeout(() => URL.revokeObjectURL(url), 10 * 60_000);
  } catch {
    win?.close();
  }
}

export function CardsPage() {
  const isAdmin = usePermission("orders.correct");
  const { data: partners = [] } = usePartners();
  const months = useMemo(() => recentMonths(13), []);
  const [partner, setPartner] = useState("");
  const [month, setMonth] = useState(months[0]);
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState<string | null>(null);

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["card-vendors", partner],
    queryFn: () => apiRequest<Vendor[]>(`/cards/vendors${partner ? `?partner=${partner}` : ""}`),
    staleTime: 60_000,
  });

  const vendors = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return (data ?? []).filter((v) => !needle || v.vendor.toLowerCase().includes(needle));
  }, [data, q]);

  async function generate(v: Vendor, withEntry: boolean) {
    const key = `${v.vendor}:${withEntry}`;
    setBusy(key);
    try {
      const p = new URLSearchParams({ vendor: v.vendor, month, with_entry: String(withEntry) });
      if (partner) p.set("partner", partner);
      await openPdf(p);
      pushToast(`${v.stores} card${v.stores > 1 ? "s" : ""} for ${v.vendor} ready.`, "success");
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Vendor cards"
        subtitle="One printable PDF per vendor — an A4 supply card for every live store, each with a QR code that shows bottles supplied."
      />

      <div className="flex flex-wrap items-end gap-3">
        <label className="flex flex-col gap-1.5 text-[13px] font-semibold text-gray-700">
          Month
          <select value={month} onChange={(e) => setMonth(e.target.value)} className="h-10 rounded-lg border border-surface-border bg-white px-3 text-sm shadow-sm">
            {months.map((m) => (
              <option key={m} value={m}>{monthLabel(m)}</option>
            ))}
          </select>
        </label>
        {isAdmin && (
          <label className="flex flex-col gap-1.5 text-[13px] font-semibold text-gray-700">
            Platform
            <select value={partner} onChange={(e) => setPartner(e.target.value)} className="h-10 rounded-lg border border-surface-border bg-white px-3 text-sm shadow-sm">
              <option value="">All platforms</option>
              {partners.map((p) => (
                <option key={p.slug} value={p.slug}>{p.name}</option>
              ))}
            </select>
          </label>
        )}
        <div className="relative ml-auto w-full sm:w-72">
          <IconSearch className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" />
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search vendor"
            aria-label="Search vendors"
            className="h-10 w-full rounded-lg border border-surface-border bg-white pl-9 pr-3 text-sm shadow-sm outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20"
          />
        </div>
      </div>

      <p className="rounded-lg bg-surface-subtle px-4 py-3 text-xs text-gray-600">
        <b>Blank cards</b> leave the dates and counts empty for hand-filling. <b>Cards with entry</b> pre-fill the month&apos;s dates, the
        filled-bottle counts and the total from marked orders; the empty-bottle and signature columns always stay blank.
      </p>

      {isLoading && <Skeleton className="h-64" />}
      {isError && <ErrorState message="Couldn't load vendors." onRetry={() => refetch()} />}
      {data && vendors.length === 0 && <EmptyState title="No vendors found" description="Try a different platform or search." />}

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {vendors.map((v) => (
          <div key={v.vendor} className="flex flex-col gap-3 rounded-xl border border-surface-border bg-white p-5 shadow-card">
            <div>
              <p className="truncate text-sm font-bold text-gray-900">{v.vendor}</p>
              <p className="text-xs text-gray-500">
                {v.stores} live store{v.stores > 1 ? "s" : ""}
                {v.number && (
                  <>
                    {" · "}
                    <a href={`tel:${v.number}`} className="font-medium text-brand-600 hover:text-brand-700">{v.number}</a>
                  </>
                )}
              </p>
            </div>
            <div className="mt-auto flex flex-wrap gap-2">
              <Button size="sm" variant="secondary" isLoading={busy === `${v.vendor}:false`} disabled={busy !== null} onClick={() => void generate(v, false)}>
                Blank cards
              </Button>
              <Button size="sm" isLoading={busy === `${v.vendor}:true`} disabled={busy !== null} onClick={() => void generate(v, true)}>
                Cards with entry
              </Button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
