import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/Button";
import { Skeleton } from "@/components/feedback/Skeleton";
import { ErrorState } from "@/components/feedback/ErrorState";
import { EmptyState } from "@/components/feedback/EmptyState";
import { IconDownload, IconSearch } from "@/components/ui/icons";
import { usePartners } from "@/features/stores/useStores";
import { usePermission } from "@/hooks/usePermission";
import { apiBlob, apiRequest } from "@/services/api";
import { camelize } from "@/lib/camel";
import { pushToast } from "@/lib/toast";

interface Vendor {
  vendor: string;
  stores: number;
  number: string | null;
}
interface VendorsResponse {
  vendors: Vendor[];
  months: { value: string; label: string }[];
}

const field =
  "h-10 rounded-lg border border-surface-border bg-white px-3 text-sm shadow-sm outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20";

function save(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 30_000);
}

/**
 * Monthwise virtual card. One PDF per vendor with an A4 card per live store: blank (a "Month of ____"
 * write-in line) or, once a month is chosen, pre-filled with that month's dates, filled bottles and total.
 * Select several vendors to get one ZIP holding a PDF for each.
 */
export function CardsPage() {
  const isAdmin = usePermission("orders.correct");
  const { data: partners = [] } = usePartners();
  const [partner, setPartner] = useState("");
  const [month, setMonth] = useState(""); // "" = blank cards
  const [q, setQ] = useState("");
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState(false);

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["card-vendors", partner],
    queryFn: async () => camelize<VendorsResponse>(await apiRequest(`/cards/vendors${partner ? `?partner=${partner}` : ""}`)),
    staleTime: 60_000,
  });

  const vendors = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return (data?.vendors ?? []).filter((v) => !needle || v.vendor.toLowerCase().includes(needle));
  }, [data, q]);

  const chosen = (data?.vendors ?? []).filter((v) => picked.has(v.vendor));
  const cardCount = chosen.reduce((n, v) => n + v.stores, 0);
  const allVisible = vendors.length > 0 && vendors.every((v) => picked.has(v.vendor));
  const monthLabel = data?.months.find((m) => m.value === month)?.label;

  function toggle(name: string) {
    setPicked((p) => {
      const next = new Set(p);
      if (next.has(name)) next.delete(name);
      else next.add(name);
      return next;
    });
  }
  function toggleAllVisible() {
    setPicked((p) => {
      const next = new Set(p);
      vendors.forEach((v) => (allVisible ? next.delete(v.vendor) : next.add(v.vendor)));
      return next;
    });
  }

  async function download(names: string[], count: number) {
    setBusy(true);
    try {
      if (names.length === 1) {
        const qs = new URLSearchParams({ vendor: names[0] });
        if (partner) qs.set("partner", partner);
        if (month) qs.set("month", month);
        // a single vendor opens as a PDF in a new tab (opened now so popup blockers allow it)
        const win = window.open("", "_blank");
        try {
          const blob = await apiBlob(`/cards/pdf?${qs}`);
          const url = URL.createObjectURL(blob);
          if (win) win.location.href = url;
          else save(blob, `cards-${names[0]}.pdf`);
          setTimeout(() => URL.revokeObjectURL(url), 10 * 60_000);
        } catch {
          win?.close();
          return;
        }
      } else {
        const blob = await apiBlob("/cards/zip", { method: "POST", body: { vendors: names, partner: partner || null, month: month || null } });
        save(blob, `Monthwise_cards_${month ? `Entry_${month}` : "Blank"}.zip`);
      }
      pushToast(`${count} card${count === 1 ? "" : "s"} for ${names.length} vendor${names.length === 1 ? "" : "s"} ready.`, "success");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Monthwise virtual card"
        subtitle="A printable A4 card for every live store, one PDF per vendor. Choose one vendor for a PDF, or several for a ZIP."
      />

      <section className="flex flex-wrap items-end gap-4 rounded-xl border border-surface-border bg-white p-4 shadow-card">
        <label className="flex flex-col gap-1.5 text-[11px] font-bold uppercase tracking-wider text-gray-500">
          Cards
          <select className={`${field} min-w-[16rem]`} value={month} onChange={(e) => setMonth(e.target.value)}>
            <option value="">Blank — no month on the card</option>
            {data?.months.map((m) => (
              <option key={m.value} value={m.value}>With entry — {m.label}</option>
            ))}
          </select>
        </label>
        {isAdmin && (
          <label className="flex flex-col gap-1.5 text-[11px] font-bold uppercase tracking-wider text-gray-500">
            Platform
            <select
              className={field}
              value={partner}
              onChange={(e) => {
                setPartner(e.target.value);
                setPicked(new Set());
              }}
            >
              <option value="">All platforms</option>
              {partners.map((p) => (
                <option key={p.slug} value={p.slug}>{p.name}</option>
              ))}
            </select>
          </label>
        )}
        <div className="relative ml-auto w-full sm:w-72">
          <IconSearch className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" />
          <input className={`${field} w-full pl-9`} value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search vendor" aria-label="Search vendors" />
        </div>
      </section>

      <p className="rounded-lg bg-surface-subtle px-4 py-3 text-xs text-gray-600">
        <b>Blank</b> cards have a &ldquo;Month of ____&rdquo; line to write on, and empty tables. <b>With entry</b> cards show the month,
        list each day that has an entry (date and filled bottles, in order) and the TOTAL COUNT; Empty bottle and Signature always stay
        blank. Every card has a QR code that opens that store&apos;s bottle count.
      </p>

      {isLoading && <Skeleton className="h-64" />}
      {isError && <ErrorState message="Couldn't load vendors." onRetry={() => refetch()} />}
      {data && vendors.length === 0 && <EmptyState title="No vendors found" description="Try a different platform or search." />}

      {data && vendors.length > 0 && (
        <div className="overflow-hidden rounded-xl border border-surface-border bg-white shadow-card">
          <div className="flex flex-wrap items-center gap-3 border-b border-surface-border bg-surface-subtle px-4 py-3">
            <label className="flex cursor-pointer items-center gap-2 text-sm font-semibold text-gray-700">
              <input type="checkbox" checked={allVisible} onChange={toggleAllVisible} className="accent-brand-500" />
              Select all{q.trim() ? " shown" : ""} ({vendors.length})
            </label>
            {picked.size > 0 && (
              <button className="text-sm font-semibold text-brand-600 hover:text-brand-700" onClick={() => setPicked(new Set())}>
                Clear selection
              </button>
            )}
            <span className="ml-auto text-sm text-gray-500">
              {picked.size > 0 ? (
                <>
                  <b className="text-gray-900">{picked.size}</b> vendor{picked.size === 1 ? "" : "s"} · <b className="text-gray-900">{cardCount}</b> cards
                </>
              ) : (
                `${data.vendors.length} vendors`
              )}
            </span>
          </div>
          <ul className="max-h-[60vh] divide-y divide-surface-border overflow-y-auto">
            {vendors.map((v) => (
              <li key={v.vendor} className={`flex items-center gap-3 px-4 py-2.5 ${picked.has(v.vendor) ? "bg-brand-50/60" : "hover:bg-surface-subtle"}`}>
                <input
                  type="checkbox"
                  aria-label={`Select ${v.vendor}`}
                  checked={picked.has(v.vendor)}
                  onChange={() => toggle(v.vendor)}
                  className="accent-brand-500"
                />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-semibold text-gray-900">{v.vendor}</p>
                  <p className="text-xs text-gray-500">
                    {v.stores} live store{v.stores === 1 ? "" : "s"}
                    {v.number ? ` · ${v.number}` : ""}
                  </p>
                </div>
                <button
                  disabled={busy}
                  onClick={() => void download([v.vendor], v.stores)}
                  className="rounded-md px-2.5 py-1 text-xs font-semibold text-brand-600 hover:bg-brand-50 disabled:opacity-50"
                >
                  PDF
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* sticky action bar */}
      <div className="sticky bottom-4 z-10 flex flex-wrap items-center gap-3 rounded-xl border border-brand-200 bg-white px-4 py-3 shadow-md">
        <p className="text-sm text-gray-600">
          {picked.size === 0
            ? "Select one or more vendors."
            : `${picked.size} vendor${picked.size === 1 ? "" : "s"} · ${cardCount} card${cardCount === 1 ? "" : "s"} · ${monthLabel ? `with entry ${monthLabel}` : "blank cards"}`}
        </p>
        <Button
          className="ml-auto"
          disabled={picked.size === 0}
          isLoading={busy}
          onClick={() => void download(chosen.map((v) => v.vendor), cardCount)}
        >
          <IconDownload className="h-4 w-4" />
          {picked.size > 1 ? `Download ZIP (${picked.size} PDFs)` : "Download PDF"}
        </Button>
      </div>
    </div>
  );
}
