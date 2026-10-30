import { useEffect, useRef } from "react";
import { Badge } from "@/components/ui/Badge";
import { Skeleton } from "@/components/feedback/Skeleton";
import { ErrorState } from "@/components/feedback/ErrorState";
import { IconClose } from "@/components/ui/icons";
import { useStoreDays, type DayCell, type ZeroFilterValues } from "@/features/zero/api";
import { StateBadge, fmtDay, fmtMoment, fmtShort } from "@/features/zero/parts";

const CELL: Record<DayCell["kind"], string> = {
  zero: "bg-rose-500/15 text-rose-700 border-rose-500/30 dark:text-rose-300",
  nonzero: "bg-emerald-500/15 text-emerald-700 border-emerald-500/30 dark:text-emerald-300",
  unmarked: "bg-surface-muted text-gray-500 border-surface-border",
  skip: "bg-surface-subtle text-gray-400 border-transparent",
  future: "bg-surface-subtle text-gray-300 border-transparent",
  holiday: "bg-sky-500/10 text-sky-700 border-sky-500/25 dark:text-sky-300",
};
const LABEL: Record<DayCell["kind"], string> = { zero: "Zero", nonzero: "Orders", unmarked: "Not marked", skip: "Not over yet", future: "Not yet", holiday: "Holiday" };

/** One store's days as a strip: zero days red, orders green, nobody reported grey, with the streak outlined and who marked each day on hover. */
export function StoreDrawer({ storeId, filters, onClose }: { storeId: string; filters: ZeroFilterValues; onClose: () => void }) {
  const q = useStoreDays(storeId, filters);
  const panel = useRef<HTMLDivElement>(null);
  useEffect(() => {
    panel.current?.focus();
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    return () => { document.removeEventListener("keydown", onKey); document.body.style.overflow = ""; };
  }, [onClose]);
  const d = q.data;
  const first = d ? new Date(`${d.days[0].date}T12:00:00`).getDay() : 0;

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <div className="absolute inset-0 animate-fade-in bg-ink-950/45 backdrop-blur-[2px]" onClick={onClose} aria-hidden="true" />
      <div ref={panel} tabIndex={-1} role="dialog" aria-modal="true" aria-label="Store days" className="relative flex h-full w-full max-w-[560px] animate-slide-in-right flex-col bg-surface-subtle shadow-lg outline-none">
        <header className="flex items-start justify-between gap-3 border-b border-surface-border bg-surface px-5 py-4">
          <div className="min-w-0">
            <p className="text-[11px] font-semibold text-gray-500">Day by day</p>
            <h2 className="truncate text-base font-extrabold text-heading">{d?.store.name ?? "…"}</h2>
            {d && <p className="text-xs text-gray-500">{d.store.outlet_id} · {fmtShort(filters.from)} to {fmtShort(filters.to)}</p>}
          </div>
          <button type="button" onClick={onClose} aria-label="Close" className="rounded-md p-1.5 text-gray-500 hover:bg-surface-muted"><IconClose className="h-5 w-5" /></button>
        </header>

        <div className="flex-1 overflow-y-auto p-5">
          {q.isLoading && <Skeleton className="h-64" />}
          {q.isError && <ErrorState message={q.error instanceof Error ? q.error.message : "Couldn't load this store."} onRetry={() => q.refetch()} />}
          {d && (
            <div className="flex flex-col gap-4">
              <div className="grid grid-cols-3 gap-2 text-center">
                {[["Longest streak", d.longest ? `${d.longest.length} d` : "none"], ["Zero days", d.total_zero], ["Unmarked", d.unmarked]].map(([k, v]) => (
                  <div key={k} className="rounded-xl border border-surface-border bg-surface px-2 py-2.5">
                    <p className="text-[11px] font-bold text-gray-400">{k}</p>
                    <p className="text-lg font-extrabold tabular-nums text-heading">{v}</p>
                  </div>
                ))}
              </div>
              {d.longest && <p className="text-sm text-gray-600">Longest run: <b>{fmtDay(d.longest.start)}</b> to <b>{fmtDay(d.longest.end)}</b>{d.longest.ongoing && <Badge tone="danger">ongoing</Badge>}</p>}
              {d.last_nonzero && <p className="text-xs text-gray-500">Last day with orders: {fmtDay(d.last_nonzero)}</p>}

              <div>
                <div className="grid grid-cols-7 gap-1.5 text-center text-[11px] font-semibold text-gray-400">
                  {["Su", "Mo", "Tu", "We", "Th", "Fr", "Sa"].map((w) => <div key={w}>{w}</div>)}
                </div>
                <div className="mt-1 grid grid-cols-7 gap-1.5">
                  {Array.from({ length: first }).map((_, i) => <div key={`b${i}`} />)}
                  {d.days.map((c) => (
                    <div key={c.date} tabIndex={0} title={`${fmtDay(c.date)} · ${LABEL[c.kind]}${c.count !== null ? ` · ${c.count}` : ""}${c.marked_by ? ` · marked by ${c.marked_by}` : ""}${c.marked_at ? ` · ${fmtMoment(c.marked_at)}` : ""}`}
                      aria-label={`${fmtDay(c.date)}: ${LABEL[c.kind]}${c.count !== null ? `, ${c.count}` : ""}`}
                      className={`flex h-12 flex-col items-center justify-center rounded-lg border text-xs ${CELL[c.kind]} ${c.in_streak ? "ring-2 ring-rose-500 ring-offset-1" : ""}`}>
                      <span className="text-[10px] opacity-70">{Number(c.date.slice(8))}</span>
                      <span className="font-bold tabular-nums">{c.count ?? (c.kind === "unmarked" ? "–" : "")}</span>
                    </div>
                  ))}
                </div>
                <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-gray-500">
                  <span><span className="mr-1 inline-block h-2.5 w-2.5 rounded-sm bg-rose-500/40" />Zero</span>
                  <span><span className="mr-1 inline-block h-2.5 w-2.5 rounded-sm bg-emerald-500/40" />Orders</span>
                  <span><span className="mr-1 inline-block h-2.5 w-2.5 rounded-sm border border-surface-border bg-surface-muted" />Not marked</span>
                  <span><span className="mr-1 inline-block h-2.5 w-2.5 rounded-sm ring-2 ring-rose-500" />In a streak</span>
                </div>
              </div>

              <section className="rounded-2xl border border-surface-border bg-surface">
                <h3 className="border-b border-surface-border px-4 py-2.5 text-sm font-bold text-heading">Who marked each zero</h3>
                <ul className="divide-y divide-surface-border">
                  {d.days.filter((c) => c.kind === "zero").length === 0 && <li className="px-4 py-3 text-sm text-gray-500">No zero days in this range.</li>}
                  {d.days.filter((c) => c.kind === "zero").map((c) => (
                    <li key={c.date} className="flex items-center justify-between gap-3 px-4 py-2 text-sm">
                      <span className="font-semibold text-gray-900">{fmtShort(c.date)}</span>
                      <span className="text-gray-600">{c.marked_by ?? "unknown"} <span className="text-xs text-gray-400">{fmtMoment(c.marked_at)}</span></span>
                    </li>
                  ))}
                </ul>
              </section>

              {d.review && (
                <section className="rounded-2xl border border-surface-border bg-surface p-4 text-sm">
                  <div className="flex items-center gap-2"><StateBadge state={d.review.status} /><span className="text-xs text-gray-500">{fmtMoment(d.review.at)}</span></div>
                  {d.review.remark && <p className="mt-2 text-gray-700">“{d.review.remark}”</p>}
                </section>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
