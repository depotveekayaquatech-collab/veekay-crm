import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Button } from "@/components/ui/Button";
import { Dropdown } from "@/components/ui/Dropdown";
import { IconCheckCircle, IconDownload, IconUsers } from "@/components/ui/icons";
import { Skeleton } from "@/components/feedback/Skeleton";
import { ErrorState } from "@/components/feedback/ErrorState";
import { downloadCsv } from "@/lib/csv";
import { copyText } from "@/lib/clipboard";
import { pushToast } from "@/lib/toast";
import { formatVendorReport } from "@/lib/vendorReport";
import { formatLimitReport } from "@/lib/zeptoLimitReport";
import { Panel, SearchBox, StatCard } from "@/features/orders/ui";
import { apiRequest } from "@/services/api";

/** monthly_limit / pending / over_by are Zepto's capping figures (daily capping x 30); null on other platforms and for a store with no capping. */
export interface VendorStore {
  store_id: string; store_name: string; external_code: string; state: string | null; city: string | null; live: boolean; bottles: number; days_marked: number;
  daily_cap: number | null; monthly_limit: number | null; pending: number | null; over_by: number | null;
}
export interface Vendor { vendor_name: string | null; vendor_number: string | null; store_count: number; bottles: number; stores: VendorStore[] }
export interface VendorPerformanceData {
  partner_slug: string; partner_label: string; month: string; month_label: string; from: string | null; to: string | null;
  summary: { vendors: number; stores: number; bottles: number };
  vendors: Vendor[];
}

export function useVendorPerformance(partner: string, month: string, enabled: boolean) {
  return useQuery({
    queryKey: ["performance", "vendors", partner, month],
    queryFn: () => apiRequest<VendorPerformanceData>(`/orders/performance/vendors?partner=${encodeURIComponent(partner)}${month ? `&month=${month}` : ""}`),
    enabled: enabled && Boolean(partner),
    refetchOnWindowFocus: true,
    staleTime: 0,
  });
}

const NO_VENDOR = "(No vendor name)";
const label = (v: Vendor) => v.vendor_name ?? NO_VENDOR;
const shortDay = (iso: string) => new Date(`${iso}T00:00:00`).toLocaleDateString("en-IN", { day: "numeric", month: "short" });
const place = (s: VendorStore) => [s.city, s.state].filter(Boolean).join(", ");

/** The text to paste: the chosen vendor, or every vendor in the list when none is chosen. Copy it, download it, or preview it first. */
function VendorReport({ d, vendors }: { d: VendorPerformanceData; vendors: Vendor[] }) {
  const [show, setShow] = useState(false);
  const period = d.from && d.to ? ` (${shortDay(d.from)} to ${shortDay(d.to)})` : "";
  const text = useMemo(
    () => d.partner_slug === "zepto"
      ? formatLimitReport(`${d.partner_label} - Vendor limit, ${d.month_label}${d.to ? ` (as on ${shortDay(d.to)})` : ""}`, vendors)
      : formatVendorReport(`${d.partner_label} - Vendor bottle count, ${d.month_label}${period}`, vendors),
    [d, vendors, period],
  );

  async function copy() {
    const ok = await copyText(text);
    pushToast(ok ? `Copied for ${vendors.length} vendor${vendors.length === 1 ? "" : "s"}. Paste it where you need it.` : "Couldn't copy. Open the preview and copy it by hand.", ok ? "success" : "error");
  }
  function download() {
    const url = URL.createObjectURL(new Blob([text], { type: "text/plain;charset=utf-8" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = `vendor-bottles-${d.partner_slug}-${d.month}.txt`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 30_000);
  }

  return (
    <div className="rounded-xl border border-surface-border bg-surface-subtle/60 p-3">
      <p className="text-xs font-bold uppercase tracking-wide text-gray-500">Text to paste</p>
      <div className="mt-2 flex flex-wrap items-center gap-2">
        <Button size="sm" onClick={() => void copy()} disabled={!vendors.length}>Copy text</Button>
        <Button size="sm" variant="secondary" onClick={download} disabled={!vendors.length}>
          <IconDownload className="h-3.5 w-3.5" aria-hidden="true" />
          Download .txt
        </Button>
        <button type="button" className="text-xs font-semibold text-brand-600 hover:text-brand-700" onClick={() => setShow((v) => !v)} aria-expanded={show}>
          {show ? "Hide preview" : "Preview"}
        </button>
      </div>
      {show && vendors.length > 0 && <textarea readOnly value={text} rows={Math.min(14, text.split("\n").length + 1)} className="mt-2 w-full resize-y rounded-lg border border-surface-border bg-surface p-3 font-mono text-xs" aria-label="Text preview" />}
    </div>
  );
}

/** Vendor-wise: pick a vendor to see each of its stores with the bottles marked this month (one row for a vendor with one store). */
export function VendorPerformance({ q }: { q: ReturnType<typeof useVendorPerformance> }) {
  const [picked, setPicked] = useState("");                 // the vendor's label; "" = the list of every vendor
  const [query, setQuery] = useState("");
  const d = q.data;

  const vendor = useMemo(() => d?.vendors.find((v) => label(v) === picked) ?? null, [d, picked]);
  const list = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return (d?.vendors ?? []).filter((v) => !needle || label(v).toLowerCase().includes(needle) || (v.vendor_number ?? "").includes(needle) || v.stores.some((s) => s.store_name.toLowerCase().includes(needle)));
  }, [d, query]);

  if (q.isLoading) return <Skeleton className="h-64 !rounded-2xl" />;
  if (q.isError) return <ErrorState message="Couldn't load the vendors." onRetry={() => q.refetch()} />;
  if (!d) return null;

  const period = d.from && d.to ? `${shortDay(d.from)} to ${shortDay(d.to)}` : "no day yet";
  const zepto = d.partner_slug === "zepto";                 // Zepto vendors have a monthly limit (capping x 30) to supply against
  const options = [{ value: "", label: `All vendors (${d.vendors.length})` }, ...d.vendors.map((v) => ({ value: label(v), label: `${label(v)} (${v.store_count} store${v.store_count === 1 ? "" : "s"})` }))];

  function exportCsv() {
    const chosen = vendor ? [vendor] : list;
    downloadCsv(
      `vendor-bottles-${d!.partner_slug}-${d!.month}${vendor ? `-${label(vendor).replace(/\W+/g, "-").toLowerCase()}` : ""}.csv`,
      ["Vendor", "Vendor number", "Store", "Store code", "City", "State", "Bottles", "Days marked", ...(zepto ? ["Monthly limit", "Pending limit"] : [])],
      chosen.flatMap((v) => v.stores.map((s) => [label(v), v.vendor_number, s.store_name, s.external_code, s.city, s.state, s.bottles, s.days_marked, ...(zepto ? [s.monthly_limit, s.pending] : [])])),
    );
  }

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-center gap-3">
        <Dropdown aria-label="Vendor" value={picked} onValueChange={setPicked} options={options} searchable className="w-full sm:w-96" />
        <Button size="sm" variant="secondary" onClick={exportCsv} disabled={!(vendor ? vendor.stores.length : list.length)}>
          <IconDownload className="h-3.5 w-3.5" aria-hidden="true" />
          Export CSV
        </Button>
        <p className="text-xs text-gray-500">Bottles marked {d.month_label}, {period}.</p>
      </div>

      <VendorReport d={d} vendors={vendor ? [vendor] : list} />

      {vendor ? (
        <>
          <div className="grid gap-4 sm:grid-cols-3">
            <StatCard label="Vendor" value={label(vendor)} hint={vendor.vendor_number ?? undefined} tone="brand" icon={IconUsers} />
            <StatCard label="Stores" value={vendor.store_count} tone="aqua" icon={IconCheckCircle} />
            <StatCard label="Bottles" value={vendor.bottles.toLocaleString()} hint={vendor.store_count === 1 ? "one store" : `across ${vendor.store_count} stores`} tone="success" icon={IconCheckCircle} />
          </div>
          <Panel flush title={<>Stores <span className="ml-1 font-medium text-gray-400">{vendor.store_count}</span></>} subtitle="Store and its bottle count this month.">
            <div className="overflow-x-auto">
              <table className="w-full min-w-[520px] text-sm">
                <thead>
                  <tr className="border-b border-surface-border bg-surface-subtle text-left text-xs font-semibold uppercase tracking-wide text-gray-500">
                    <th className="px-5 py-3">Store</th><th className="px-4 py-3">Place</th><th className="px-4 py-3 text-right">Days marked</th>
                    {zepto && <><th className="px-4 py-3 text-right">Monthly limit</th><th className="px-4 py-3 text-right">Pending limit</th></>}
                    <th className="px-5 py-3 text-right">{zepto ? "Supplied" : "Bottles"}</th>
                  </tr>
                </thead>
                <tbody>
                  {vendor.stores.map((s) => (
                    <tr key={s.store_id} className="border-b border-surface-border">
                      <td className="px-5 py-3">
                        <div className="font-semibold text-gray-900">{s.store_name}</div>
                        <div className="text-xs text-gray-500">{s.external_code}{s.live ? "" : " · not live"}</div>
                      </td>
                      <td className="px-4 py-3 text-gray-600">{place(s) || "—"}</td>
                      <td className="px-4 py-3 text-right tabular-nums">{s.days_marked}</td>
                      {zepto && (
                        <>
                          <td className="px-4 py-3 text-right tabular-nums">{s.monthly_limit === null ? "—" : s.monthly_limit.toLocaleString("en-IN")}</td>
                          <td className={`px-4 py-3 text-right font-semibold tabular-nums ${s.pending === 0 ? "text-status-danger" : ""}`}>{s.pending === null ? "—" : s.pending.toLocaleString("en-IN")}</td>
                        </>
                      )}
                      <td className="px-5 py-3 text-right text-base font-extrabold tabular-nums text-heading">{s.bottles.toLocaleString()}</td>
                    </tr>
                  ))}
                  {vendor.store_count > 1 && (
                    <tr className="bg-surface-subtle/60 font-bold">
                      <td className="px-5 py-3" colSpan={zepto ? 5 : 3}>Total, {vendor.store_count} stores</td>
                      <td className="px-5 py-3 text-right text-base tabular-nums text-heading">{vendor.bottles.toLocaleString()}</td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </Panel>
        </>
      ) : (
        <>
          <div className="grid gap-4 sm:grid-cols-3">
            <StatCard label="Vendors" value={d.summary.vendors} tone="brand" icon={IconUsers} />
            <StatCard label="Stores" value={d.summary.stores.toLocaleString()} tone="aqua" icon={IconCheckCircle} />
            <StatCard label="Bottles" value={d.summary.bottles.toLocaleString()} tone="success" icon={IconCheckCircle} />
          </div>
          <Panel
            flush
            title={<>Vendors <span className="ml-1 font-medium text-gray-400">{list.length}</span></>}
            subtitle="Choose a vendor above, or open one here, to see its stores."
            action={<SearchBox hotkey value={query} onChange={setQuery} placeholder="Search vendor, number or store" className="w-full sm:w-64" />}
          >
            <div className="overflow-x-auto">
              <table className="w-full min-w-[520px] text-sm">
                <thead>
                  <tr className="border-b border-surface-border bg-surface-subtle text-left text-xs font-semibold uppercase tracking-wide text-gray-500">
                    <th className="px-5 py-3">Vendor</th><th className="px-4 py-3 text-right">Stores</th><th className="px-5 py-3 text-right">Bottles</th>
                  </tr>
                </thead>
                <tbody>
                  {list.length === 0 && <tr><td colSpan={3} className="px-4 py-12 text-center text-gray-500">No vendors match.</td></tr>}
                  {list.map((v) => (
                    <tr key={label(v)} className="cursor-pointer border-b border-surface-border hover:bg-surface-subtle/70" onClick={() => setPicked(label(v))}>
                      <td className="px-5 py-3">
                        <div className="font-semibold text-gray-900">{label(v)}</div>
                        {v.vendor_number && <div className="text-xs text-gray-500">{v.vendor_number}</div>}
                      </td>
                      <td className="px-4 py-3 text-right tabular-nums">{v.store_count}</td>
                      <td className="px-5 py-3 text-right font-bold tabular-nums text-heading">{v.bottles.toLocaleString()}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Panel>
        </>
      )}
    </div>
  );
}
