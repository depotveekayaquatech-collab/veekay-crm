import { useMemo, useState, type FormEvent } from "react";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import type { CalendarDay, OrderCalendar as Cal } from "@/types/order";

const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

function Chevron({ dir }: { dir: "left" | "right" }) {
  return (
    <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d={dir === "left" ? "M15 6l-6 6 6 6" : "M9 6l6 6-6 6"} />
    </svg>
  );
}

function dayTone(d: CalendarDay, clickable: boolean): string {
  if (d.marked) {
    return d.source === "admin"
      ? "border-status-warning/30 bg-status-warning-soft text-status-warning"
      : "border-status-success/25 text-status-success";
  }
  if (d.isFuture) return "border-transparent bg-surface-subtle text-gray-300";
  return clickable
    ? "border-dashed border-gray-300 bg-surface text-gray-700 hover:border-brand-400 hover:bg-brand-50"
    : "border-dashed border-gray-300 bg-surface text-gray-500";
}

interface Props {
  calendar: Cal;
  /** null when the viewer can't mark (e.g. admin uses CorrectEntryModal instead). */
  onMark?: (date: string, count: number) => Promise<unknown>;
  onPickDay?: (day: CalendarDay) => void;
  marking?: boolean;
  /** Month stepping. Omit to hide the arrows. */
  onNavigate?: (year: number, month: number) => void;
}

export function OrderCalendar({ calendar, onMark, onPickDay, marking, onNavigate }: Props) {
  const [selected, setSelected] = useState<CalendarDay | null>(null);
  const [count, setCount] = useState("");

  const firstWeekday = new Date(calendar.year, calendar.month - 1, 1).getDay();
  const blanks = Array.from({ length: firstWeekday });

  const stats = useMemo(() => {
    const past = calendar.days.filter((d) => !d.isFuture);
    const marked = calendar.days.filter((d) => d.marked);
    const bottles = marked.reduce((s, d) => s + (d.count ?? 0), 0);
    return {
      bottles,
      marked: marked.length,
      elapsed: past.length,
      missing: past.length - marked.filter((d) => !d.isFuture).length,
      avg: marked.length ? Math.round(bottles / marked.length) : 0,
    };
  }, [calendar]);

  // Busier days get a stronger tint, so the month reads like a heat-map at a glance.
  const maxCount = useMemo(() => Math.max(1, ...calendar.days.map((d) => d.count ?? 0)), [calendar]);

  const now = new Date();
  const isCurrentMonth = calendar.year === now.getFullYear() && calendar.month === now.getMonth() + 1;

  function step(delta: number) {
    if (!onNavigate) return;
    const d = new Date(calendar.year, calendar.month - 1 + delta, 1);
    setSelected(null);
    onNavigate(d.getFullYear(), d.getMonth() + 1);
  }

  const canMark = Boolean(onMark);
  function pick(d: CalendarDay) {
    if (onPickDay) {
      onPickDay(d);
      return;
    }
    if (d.marked || d.isFuture || !onMark) return;
    setSelected(d);
    setCount("");
  }

  const n = Number(count);
  const valid = count !== "" && Number.isInteger(n) && n >= 0 && n <= 200;

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!selected || !onMark || !valid) return;
    await onMark(selected.date, n);
    setSelected(null);
    setCount("");
  }

  return (
    <div className="overflow-hidden rounded-2xl border border-surface-border bg-surface shadow-card">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-surface-border px-4 py-3.5 sm:px-5">
        <div className="flex items-center gap-1">
          {onNavigate && (
            <button
              type="button"
              onClick={() => step(-1)}
              aria-label="Previous month"
              className="rounded-md p-1.5 text-gray-500 hover:bg-surface-muted hover:text-gray-900"
            >
              <Chevron dir="left" />
            </button>
          )}
          <h3 className="min-w-[9rem] text-center text-base font-extrabold text-heading">{calendar.monthLabel}</h3>
          {onNavigate && (
            <button
              type="button"
              onClick={() => step(1)}
              disabled={isCurrentMonth}
              aria-label="Next month"
              className="rounded-md p-1.5 text-gray-500 hover:bg-surface-muted hover:text-gray-900 disabled:cursor-not-allowed disabled:opacity-30 disabled:hover:bg-transparent"
            >
              <Chevron dir="right" />
            </button>
          )}
          {onNavigate && !isCurrentMonth && (
            <button
              type="button"
              onClick={() => onNavigate(now.getFullYear(), now.getMonth() + 1)}
              className="ml-1 rounded-md px-2 py-1 text-xs font-semibold text-brand-600 hover:bg-brand-50"
            >
              Today
            </button>
          )}
        </div>
        <div className="flex gap-3 text-xs text-gray-500">
          <span className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-sm bg-status-success" /> Employee</span>
          <span className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-sm bg-status-warning" /> Admin</span>
          <span className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-sm border border-dashed border-gray-400" /> Missing</span>
        </div>
      </div>

      <div className="grid grid-cols-2 divide-x divide-y divide-surface-border border-b border-surface-border sm:grid-cols-4 sm:divide-y-0">
        {[
          { label: "Bottles", value: stats.bottles, tone: "text-heading" },
          { label: "Days marked", value: `${stats.marked}/${stats.elapsed}`, tone: "text-heading" },
          { label: "Missing", value: stats.missing, tone: stats.missing > 0 ? "text-status-warning" : "text-status-success" },
          { label: "Avg / day", value: stats.avg, tone: "text-heading" },
        ].map((s) => (
          <div key={s.label} className="px-4 py-3 sm:px-5">
            <p className="text-[10px] font-bold uppercase tracking-wider text-gray-400">{s.label}</p>
            <p className={`mt-0.5 text-lg font-bold tabular-nums ${s.tone}`}>{s.value}</p>
          </div>
        ))}
      </div>

      <div className="p-3 sm:p-5">
        <div className="grid grid-cols-7 gap-1.5 text-center text-[11px] font-semibold uppercase tracking-wide text-gray-400 sm:gap-2">
          {WEEKDAYS.map((w) => (
            <div key={w} className="pb-1">{w}</div>
          ))}
        </div>
        <div className="mt-1 grid grid-cols-7 gap-1.5 sm:gap-2">
          {blanks.map((_, i) => (
            <div key={`b${i}`} />
          ))}
          {calendar.days.map((d) => {
            const clickable = Boolean(onPickDay) || (canMark && !d.marked && !d.isFuture);
            const isSel = selected?.date === d.date;
            return (
              <button
                key={d.day}
                type="button"
                onClick={() => pick(d)}
                disabled={!clickable}
                title={d.marked ? `${d.count} bottles (${d.source})` : d.isFuture ? undefined : "Not marked"}
                style={d.marked && d.source !== "admin" ? { backgroundColor: `rgb(var(--success) / ${0.1 + 0.3 * ((d.count ?? 0) / maxCount)})` } : undefined}
                className={`relative flex h-14 flex-col sm:h-[4.25rem] items-center justify-center rounded-lg border text-sm transition-[transform,box-shadow,background-color,border-color] disabled:cursor-default ${dayTone(d, clickable)} ${
                  d.isToday ? "ring-2 ring-brand-400 ring-offset-1" : ""
                } ${isSel ? "scale-[1.04] border-brand-500 bg-brand-50 text-brand-700 shadow-md" : ""}`}
              >
                <span className={`absolute left-1.5 top-1 text-[10px] font-semibold ${d.marked ? "opacity-70" : ""}`}>{d.day}</span>
                {d.marked ? (
                  <span className="text-base font-bold tabular-nums">{d.count}</span>
                ) : !d.isFuture ? (
                  <span className="text-lg font-light text-gray-300">+</span>
                ) : null}
              </button>
            );
          })}
        </div>

        {selected && onMark && (
          <form onSubmit={submit} className="mt-5 flex flex-wrap items-end gap-3 rounded-lg border border-brand-100 bg-brand-50/60 p-3.5">
            <div className="min-w-[10rem] flex-1">
              <Input
                label={`Bottles for ${selected.date}`}
                type="number"
                inputMode="numeric"
                min={0}
                max={200}
                value={count}
                onChange={(e) => setCount(e.target.value)}
                autoFocus
                hint="0–200. Zero is a valid count."
              />
            </div>
            <Button type="submit" isLoading={marking} disabled={!valid}>
              Save entry
            </Button>
            <Button type="button" variant="ghost" onClick={() => setSelected(null)} disabled={marking}>
              Cancel
            </Button>
          </form>
        )}
        {!selected && canMark && stats.missing > 0 && (
          <p className="mt-4 text-center text-xs text-gray-500">Tap a dashed day to add its bottle count.</p>
        )}
      </div>
    </div>
  );
}
