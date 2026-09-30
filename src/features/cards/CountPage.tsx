import { useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { apiRequest } from "@/services/api";
import { camelize } from "@/lib/camel";

interface PublicCount {
  storeName: string;
  storeCode: string;
  platform: string | null;
  city: string | null;
  state: string | null;
  thisMonthLabel: string;
  thisMonthBottles: number;
  thisMonthEntries: number;
  lastMonthLabel: string;
  lastMonthBottles: number;
  lastMonthEntries: number;
  daily: { date: string; bottles: number }[];
}

/** Public page opened by the QR code on a vendor card. No login: the signed link is the key. */
export function CountPage() {
  const [params] = useSearchParams();
  const s = params.get("s");
  const sig = params.get("sig");

  const { data, isLoading, isError } = useQuery({
    queryKey: ["public-count", s, sig],
    queryFn: async () =>
      camelize<PublicCount>(await apiRequest(`/public/count?s=${encodeURIComponent(s ?? "")}&sig=${encodeURIComponent(sig ?? "")}`, { silent: true })),
    enabled: Boolean(s && sig),
    retry: false,
  });

  const max = Math.max(1, ...(data?.daily.map((d) => d.bottles) ?? [1]));

  return (
    <div className="min-h-screen bg-surface-subtle px-4 py-6 sm:py-10">
      <div className="mx-auto w-full max-w-md">
        <div className="mb-5 flex items-center gap-2.5">
          <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-brand-400 via-brand-600 to-aqua-500 text-sm font-extrabold text-white shadow-glow">V</span>
          <div className="leading-tight">
            <p className="text-sm font-bold text-ink-900">Veekay Aquatech</p>
            <p className="text-[11px] text-gray-500">Bottles supplied</p>
          </div>
        </div>

        {(!s || !sig || isError) && (
          <div className="rounded-xl border border-surface-border bg-white p-6 text-center shadow-card">
            <p className="text-base font-bold text-ink-900">This QR code isn&apos;t valid</p>
            <p className="mt-1 text-sm text-gray-500">Please scan the code printed on your Veekay supply card again.</p>
          </div>
        )}

        {isLoading && <div className="h-64 animate-pulse rounded-xl bg-surface-muted" />}

        {data && (
          <div className="flex flex-col gap-4">
            <div className="rounded-xl border border-surface-border bg-white p-5 shadow-card">
              <p className="text-lg font-bold leading-snug text-ink-900">{data.storeName}</p>
              <p className="mt-0.5 text-xs text-gray-500">
                {[data.storeCode, data.platform, [data.city, data.state].filter(Boolean).join(", ")].filter(Boolean).join(" · ")}
              </p>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div className="tile tile-brand rounded-xl border border-surface-border bg-white p-4 shadow-card">
                <p className="text-[11px] font-bold uppercase tracking-wider text-gray-500">{data.thisMonthLabel}</p>
                <p className="mt-1.5 text-3xl font-bold leading-none tabular-nums text-ink-900">{data.thisMonthBottles.toLocaleString()}</p>
                <p className="mt-1 text-xs text-gray-500">bottles · {data.thisMonthEntries} day{data.thisMonthEntries === 1 ? "" : "s"}</p>
              </div>
              <div className="tile tile-aqua rounded-xl border border-surface-border bg-white p-4 shadow-card">
                <p className="text-[11px] font-bold uppercase tracking-wider text-gray-500">{data.lastMonthLabel}</p>
                <p className="mt-1.5 text-3xl font-bold leading-none tabular-nums text-ink-900">{data.lastMonthBottles.toLocaleString()}</p>
                <p className="mt-1 text-xs text-gray-500">bottles · {data.lastMonthEntries} day{data.lastMonthEntries === 1 ? "" : "s"}</p>
              </div>
            </div>

            {data.daily.length > 0 && (
              <div className="rounded-xl border border-surface-border bg-white p-5 shadow-card">
                <p className="mb-3 text-sm font-bold text-gray-900">{data.thisMonthLabel} — day by day</p>
                <ul className="flex flex-col gap-2">
                  {data.daily.map((d) => (
                    <li key={d.date} className="flex items-center gap-3 text-xs">
                      <span className="w-14 shrink-0 text-gray-500">{new Date(`${d.date}T12:00:00`).toLocaleDateString(undefined, { day: "2-digit", month: "short" })}</span>
                      <div className="h-2 flex-1 overflow-hidden rounded-full bg-surface-muted">
                        <div className="h-full rounded-full bg-brand-500" style={{ width: `${(d.bottles / max) * 100}%` }} />
                      </div>
                      <span className="w-8 shrink-0 text-right font-semibold tabular-nums text-gray-800">{d.bottles}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
