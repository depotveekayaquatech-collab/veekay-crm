import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import type { CalendarDay, OrderCalendar as Cal } from "@/types/order";

const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

function dayTone(d: CalendarDay): string {
  if (!d.marked) {
    if (d.isFuture) return "bg-surface-subtle text-gray-300";
    return "bg-white hover:border-brand-400 hover:bg-brand-50 cursor-pointer";
  }
  if (d.source === "admin") return "bg-status-warning-soft text-status-warning border-status-warning/30";
  return "bg-status-success-soft text-status-success border-status-success/30";
}

interface Props {
  calendar: Cal;
  /** null when the viewer can't mark (e.g. admin uses CorrectEntryModal instead). */
  onMark?: (date: string, count: number) => Promise<unknown>;
  onPickDay?: (day: CalendarDay) => void;
  marking?: boolean;
}

export function OrderCalendar({ calendar, onMark, onPickDay, marking }: Props) {
  const [selected, setSelected] = useState<CalendarDay | null>(null);
  const [count, setCount] = useState("");

  const firstWeekday = new Date(calendar.year, calendar.month - 1, 1).getDay();
  const blanks = Array.from({ length: firstWeekday });

  function pick(d: CalendarDay) {
    if (onPickDay) {
      onPickDay(d);
      return;
    }
    if (d.marked || d.isFuture || !onMark) return;
    setSelected(d);
    setCount("");
  }

  async function submit() {
    if (!selected || !onMark) return;
    const n = Number(count);
    if (!Number.isInteger(n) || n < 0 || n > 200) return;
    await onMark(selected.date, n);
    setSelected(null);
    setCount("");
  }

  return (
    <div className="rounded-lg border border-surface-border bg-white p-4 shadow-card">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-gray-900">{calendar.monthLabel}</h3>
        <div className="flex gap-3 text-xs text-gray-500">
          <span className="flex items-center gap-1"><span className="h-2 w-2 rounded-full bg-status-success" /> Employee</span>
          <span className="flex items-center gap-1"><span className="h-2 w-2 rounded-full bg-status-warning" /> Admin</span>
        </div>
      </div>

      <div className="grid grid-cols-7 gap-1 text-center text-[11px] font-medium uppercase text-gray-400">
        {WEEKDAYS.map((w) => (
          <div key={w} className="py-1">{w}</div>
        ))}
      </div>
      <div className="mt-1 grid grid-cols-7 gap-1 sm:gap-1.5">
        {blanks.map((_, i) => (
          <div key={`b${i}`} />
        ))}
        {calendar.days.map((d) => (
          <button
            key={d.day}
            type="button"
            onClick={() => pick(d)}
            disabled={!onPickDay && (d.marked || d.isFuture)}
            className={`flex aspect-square flex-col items-center justify-center rounded-md border border-surface-border p-1 text-sm transition-colors disabled:cursor-default ${dayTone(d)} ${
              d.isToday ? "ring-2 ring-brand-400" : ""
            }`}
          >
            <span className="font-medium">{d.day}</span>
            {d.marked && <span className="text-[11px] font-semibold tabular-nums">{d.count}</span>}
          </button>
        ))}
      </div>

      {selected && onMark && (
        <div className="mt-4 flex flex-wrap items-end gap-3 rounded-md bg-surface-subtle p-3">
          <div className="flex-1 min-w-[8rem]">
            <Input
              label={`Bottles for ${selected.date}`}
              type="number"
              min={0}
              max={200}
              value={count}
              onChange={(e) => setCount(e.target.value)}
              autoFocus
              hint="0–200. Zero is a valid count."
            />
          </div>
          <Button onClick={submit} isLoading={marking} disabled={count === ""}>
            Mark
          </Button>
          <Button variant="ghost" onClick={() => setSelected(null)} disabled={marking}>
            Cancel
          </Button>
        </div>
      )}
    </div>
  );
}
