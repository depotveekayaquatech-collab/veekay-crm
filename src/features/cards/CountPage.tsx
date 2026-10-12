import { SelectField } from "@/components/ui/Dropdown";
import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { BrandLogo } from "@/components/ui/BrandLogo";
import { ApiError, apiRequest } from "@/services/api";
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
  const s = params.get("s")?.trim();
  const sig = params.get("sig")?.trim();
  const [view, setView] = useState<"cur" | "last">("cur");

  const { data, isLoading, isError, error, refetch, isFetching } = useQuery({
    queryKey: ["public-count", s, sig],
    queryFn: async () =>
      camelize<PublicCount>(
        await apiRequest(`/public/count?s=${encodeURIComponent(s ?? "")}&sig=${encodeURIComponent(sig ?? "")}`, {
          silent: true,
        }),
      ),
    enabled: Boolean(s && sig),
    retry: (failureCount, err) => {
      // Don't retry invalid signatures or nonexistent stores
      if (err instanceof ApiError && (err.status === 404 || err.status === 422)) {
        return false;
      }
      // Retry temporary network errors / backend spin-ups
      return failureCount < 3;
    },
    retryDelay: (attempt) => Math.min(1000 * 2 ** attempt, 3000),
  });

  const hasLast = Boolean(data?.lastMonthLabel);
  const showing =
    data &&
    (view === "last" && hasLast
      ? { label: data.lastMonthLabel as string, title: "Full month", total: data.lastMonthBottles ?? 0 }
      : { label: data.thisMonthLabel, title: "Till date", total: data.thisMonthBottles });

  const isInvalidParams = !s || !sig;
  const isInvalidSignature = error instanceof ApiError && (error.status === 404 || error.status === 422);
  const isNetworkOrColdStart = isError && !isInvalidSignature;

  return (
    <div className="min-h-screen bg-[#eaf3fa]">
      <div className="bg-[#0B6FB8] px-3 py-2.5 text-center text-sm font-bold tracking-wider text-white">
        VEE KAY AQUATECH PVT. LTD.
      </div>
      <div className="flex justify-center border-b-4 border-[#0B6FB8] bg-white py-3">
        <BrandLogo height={64} />
      </div>

      <div className="mx-auto mt-4 w-full max-w-md px-4 pb-12">
        {isInvalidParams && (
          <div className="rounded-2xl border border-rose-100 bg-white p-6 text-center shadow-card">
            <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-rose-50 text-xl text-rose-600">
              ⚠️
            </div>
            <h2 className="mt-3 text-base font-bold text-ink-900">Missing QR Parameters</h2>
            <p className="mt-1 text-sm text-gray-500">
              This link is missing store verification parameters. Please scan the QR code printed on the physical Veekay card again.
            </p>
          </div>
        )}

        {isInvalidSignature && (
          <div className="rounded-2xl border border-rose-100 bg-white p-6 text-center shadow-card">
            <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-rose-50 text-xl text-rose-600">
              ✕
            </div>
            <h2 className="mt-3 text-base font-bold text-ink-900">Invalid or Expired QR Code</h2>
            <p className="mt-1 text-sm text-gray-500">
              This QR code could not be verified or the store is no longer active. Please scan the code printed on your physical card again.
            </p>
          </div>
        )}

        {isNetworkOrColdStart && (
          <div className="rounded-2xl border border-amber-200 bg-white p-6 text-center shadow-card">
            <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-amber-50 text-xl text-amber-600">
              🔄
            </div>
            <h2 className="mt-3 text-base font-bold text-ink-900">Connecting to Server</h2>
            <p className="mt-1 text-sm text-gray-500">
              The server may be starting up or the network signal was interrupted.
            </p>
            <button
              type="button"
              onClick={() => refetch()}
              disabled={isFetching}
              className="mt-4 inline-flex items-center justify-center rounded-xl bg-[#0B6FB8] px-5 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-[#084B7C] disabled:opacity-50"
            >
              {isFetching ? "Reconnecting..." : "Try Again"}
            </button>
          </div>
        )}

        {isLoading && !isError && (
          <div className="space-y-4 rounded-2xl bg-white/80 p-6 text-center shadow-card backdrop-blur">
            <div className="mx-auto h-8 w-32 animate-pulse rounded-full bg-slate-200" />
            <div className="mx-auto h-6 w-3/4 animate-pulse rounded bg-slate-200" />
            <div className="mx-auto h-4 w-1/2 animate-pulse rounded bg-slate-200" />
            <div className="mx-auto my-6 h-28 w-44 animate-pulse rounded-2xl bg-slate-200" />
            <p className="text-xs font-semibold text-[#0B6FB8]">Fetching verified bottle count...</p>
          </div>
        )}

        {data && showing && (
          <div className="rounded-2xl border border-sky-100 bg-white p-5 text-center shadow-card">
            <div className="inline-flex items-center gap-1.5 rounded-full bg-[#e8f2fa] px-3 py-1 text-xs font-bold text-[#084B7C]">
              <span className="h-2 w-2 rounded-full bg-emerald-500" />
              Verified Store Card
            </div>

            <h1 className="mt-2 text-xl font-bold leading-snug text-ink-900">{data.storeName}</h1>
            <p className="mt-0.5 text-xs text-gray-500">
              ID: <b className="font-mono text-gray-800">{data.storeCode}</b>
              {data.vendorName ? <> · Vendor: <b>{data.vendorName}</b></> : null}
              {data.platform ? <> · Platform: <b>{data.platform}</b></> : null}
            </p>

            {hasLast ? (
              <div className="mt-5 text-left">
                <label htmlFor="month" className="mb-1.5 block text-xs font-bold text-[#084B7C]">
                  View supply for
                </label>
                <SelectField
                  id="month"
                  value={view}
                  onChange={(e) => setView(e.target.value as "cur" | "last")}
                  className="h-12 w-full rounded-xl border-2 border-[#0B6FB8] bg-[#f4f9fd] px-4 text-[15px] font-bold text-[#084B7C] outline-none"
                >
                  <option value="cur">This month — {data.thisMonthLabel}</option>
                  <option value="last">Last month — {data.lastMonthLabel}</option>
                </SelectField>
              </div>
            ) : (
              <span className="mt-5 inline-block rounded-full bg-[#e8f2fa] px-4 py-1.5 text-xs font-bold text-[#084B7C]">
                {showing.label} • {showing.title}
              </span>
            )}

            <div className="mt-5 rounded-2xl border border-slate-100 bg-slate-50/70 p-5">
              <p className="text-xs font-bold uppercase tracking-wider text-gray-500">
                {showing.label} • {showing.title}
              </p>
              <p className="mt-2 text-6xl font-extrabold leading-tight tabular-nums text-[#0B6FB8]">
                {showing.total}
              </p>
              <p className="text-xs font-semibold text-gray-500">bottles supplied</p>
            </div>

            <div className="mt-5 flex items-center justify-between text-left text-xs text-gray-400">
              <span>
                As on {new Date(data.asOn).toLocaleString(undefined, {
                  day: "numeric",
                  month: "short",
                  year: "numeric",
                  hour: "2-digit",
                  minute: "2-digit",
                })}
              </span>
              <button
                type="button"
                onClick={() => refetch()}
                disabled={isFetching}
                className="text-xs font-bold text-[#0B6FB8] hover:underline disabled:opacity-50"
              >
                {isFetching ? "Updating..." : "Refresh"}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
