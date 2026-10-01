import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { BrandLogo } from "@/components/ui/BrandLogo";
import { apiRequest } from "@/services/api";
import { camelize } from "@/lib/camel";

interface PublicCount {
  storeName: string;
  storeCode: string;
  vendorName: string | null;
  platform: string | null;
  thisMonthLabel: string;
  thisMonthBottles: number;
  lastMonthLabel: string | null;
  lastMonthBottles: number | null;
  asOn: string;
}

/**
 * Public page opened by the QR code on a card. No login: the signed link is the key.
 * Shows the month's bottle total only — this month till date, and last month once it is an active month.
 */
export function CountPage() {
  const [params] = useSearchParams();
  const s = params.get("s");
  const sig = params.get("sig");
  const [view, setView] = useState<"cur" | "last">("cur");

  const { data, isLoading, isError } = useQuery({
    queryKey: ["public-count", s, sig],
    queryFn: async () =>
      camelize<PublicCount>(await apiRequest(`/public/count?s=${encodeURIComponent(s ?? "")}&sig=${encodeURIComponent(sig ?? "")}`, { silent: true })),
    enabled: Boolean(s && sig),
    retry: false,
  });

  const hasLast = Boolean(data?.lastMonthLabel);
  const showing =
    data && (view === "last" && hasLast
      ? { label: data.lastMonthLabel as string, title: "Full month", total: data.lastMonthBottles ?? 0 }
      : { label: data.thisMonthLabel, title: "Till date", total: data.thisMonthBottles });

  return (
    <div className="min-h-screen bg-[#eaf3fa]">
      <div className="bg-[#0B6FB8] px-3 py-2.5 text-center text-sm font-bold tracking-wider text-white">VEE KAY AQUATECH PVT. LTD.</div>
      <div className="flex justify-center border-b-4 border-[#0B6FB8] bg-white py-3">
        <BrandLogo height={64} />
      </div>

      <div className="mx-auto mt-4 w-full max-w-md px-4 pb-10">
        {(!s || !sig || isError) && (
          <div className="rounded-2xl bg-white p-6 text-center shadow">
            <p className="text-base font-bold text-ink-900">Invalid or tampered QR code.</p>
            <p className="mt-1 text-sm text-gray-500">Please scan the code printed on your Veekay card again.</p>
          </div>
        )}
        {isLoading && <div className="h-64 animate-pulse rounded-2xl bg-white/70" />}

        {data && showing && (
          <div className="rounded-2xl bg-white p-5 text-center shadow">
            <p className="text-xs text-gray-500">Store</p>
            <h1 className="mt-1 text-lg font-bold leading-snug text-ink-900">{data.storeName}</h1>
            <p className="text-xs text-gray-500">
              ID: <b>{data.storeCode}</b>
              {data.vendorName ? <> · Vendor: <b>{data.vendorName}</b></> : null}
            </p>

            {hasLast ? (
              <div className="mt-4 text-left">
                <label htmlFor="month" className="mb-1.5 block text-xs font-bold text-[#084B7C]">View supply for</label>
                <select
                  id="month"
                  value={view}
                  onChange={(e) => setView(e.target.value as "cur" | "last")}
                  className="h-12 w-full rounded-xl border-2 border-[#0B6FB8] bg-[#f4f9fd] px-4 text-[15px] font-bold text-[#084B7C] outline-none"
                >
                  <option value="cur">This month — {data.thisMonthLabel}</option>
                  <option value="last">Last month — {data.lastMonthLabel}</option>
                </select>
              </div>
            ) : (
              <span className="mt-4 inline-block rounded-full bg-[#e8f2fa] px-4 py-1.5 text-xs font-bold text-[#084B7C]">
                {showing.label} • {showing.title}
              </span>
            )}

            <div className="mt-4">
              <p className="text-xs text-gray-500">
                {showing.label} • {showing.title}
              </p>
              <p className="mt-2 text-6xl font-bold leading-tight tabular-nums text-[#0B6FB8]">{showing.total}</p>
              <p className="text-xs text-gray-500">bottles supplied</p>
            </div>
            <p className="mt-5 text-xs text-gray-500">
              As on {new Date(data.asOn).toLocaleString(undefined, { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" })}
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
