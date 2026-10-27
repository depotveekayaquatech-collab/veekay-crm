import { useMemo, useState, type FormEvent } from "react";
import { MAX_BOTTLES } from "@/features/orders/limits";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import type { CalendarDay, OrderCalendar as Cal } from "@/types/order";
import { fmtMomentShort } from "@/features/entries/format";

const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

function Chevron({ dir }: { dir: "left" | "right" }) {
  return (
    <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d={dir === "left" ? "M15 6l-6 6 6 6" : "M9 6l6 6-6 6"} />
    </svg>
  );
}

/**
 * What happened to this person's entries after they saved them: who changed the number (name and role), when, from what to what, why, and where the
 * entry stands now. It comes from the server's append-only history, so it is always the real record.
 */
function ChangedByList({ days }: { days: CalendarDay[] }) {
  const changed = days.filter((d) => d.changed && !d.masked);
  const states = days.filter((d) => d.verification && d.mine && !d.masked);
  if (changed.length === 0 && states.length === 0) return null;
  const tone = { submitted: "bg-amber-500/10 text-amber-800 dark:text-amber-300", verified_l2: "bg-sky-500/10 text-sky-800 dark:text-sky-300", reviewed_l3: "bg-emerald-500/10 text-emerald-800 dark:text-emerald-300" } as const;
  return (
    <div className="mt-5 flex flex-col gap-3 rounded-xl border border-surface-border bg-surface-subtle p-3.5">
      {changed.length > 0 && (
        <div>
          <h4 className="text-sm font-bold text-heading">Changes to your entries</h4>
          <ul className="mt-2 flex flex-col gap-2">
            {[...changed].reverse().map((d) => (
              <li key={d.date} className="rounded-lg bg-surface px-3 py-2 text-sm ring-1 ring-surface-border">
                <p className="font-semibold text-gray-900">
                  {d.date}: <span className="text-gray-500 line-through">{d.changed!.oldCount}</span> → <span className="text-brand-700">{d.changed!.newCount}</span> bottles
                </p>
                <p className="text-xs text-gray-600">
                  Changed by <b>{d.changed!.byName ?? "a senior colleague"}</b> – {d.changed!.byRoleLabel}, {fmtMomentShort(d.changed!.at)}
                  {d.changed!.reason ? ` · "${d.changed!.reason}"` : ""}
                </p>
              </li>
            ))}
          </ul>
        </div>
      )}
      {states.length > 0 && (
        <div>
          <h4 className="text-sm font-bold text-heading">Where your entries stand</h4>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {states.map((d) => (
              <span key={d.date} className={`rounded-full px-2.5 py-1 text-xs font-semibold ${tone[d.verification!.status]}`}>
                {d.date.slice(5)}: {d.verification!.label}{d.verification!.byName ? ` (${d.verification!.byName})` : ""}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function dayTone(d: CalendarDay, clickable: boolean): string {
  if (d.marked && d.masked) return "border-surface-border bg-surface-muted text-gray-500";   // a colleague marked it: shown as done, no number
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
  /** Lets an employee correct (or, with null, remove) a day they marked themselves. */
  onCorrect?: (date: string, count: number | null) => Promise<unknown>;
  /** Batch mark multiple dates in one request */
  onMarkMany?: (entries: { orderDate: string; bottleCount: number }[]) => Promise<unknown>;
  onPickDay?: (day: CalendarDay) => void;
  marking?: boolean;
  /** Month stepping. Omit to hide the arrows. */
  onNavigate?: (year: number, month: number) => void;
  isAdmin?: boolean;
}

export function OrderCalendar({ calendar, onMark, onCorrect, onMarkMany, onPickDay, marking, onNavigate, isAdmin }: Props) {
  const [selected, setSelected] = useState<CalendarDay | null>(null);
  const [count, setCount] = useState("");

  // Multi-date selection state
  const [multiMode, setMultiMode] = useState(false);
  const [selectedDates, setSelectedDates] = useState<Set<string>>(new Set());
  const [multiCount, setMultiCount] = useState("");
  const [customCounts, setCustomCounts] = useState<Record<string, string>>({});
  const [customizeEach, setCustomizeEach] = useState(false);

  const firstWeekday = new Date(calendar.year, calendar.month - 1, 1).getDay();
  const blanks = Array.from({ length: firstWeekday });

  const missingDays = useMemo(() => {
    return calendar.days.filter((d) => (isAdmin ? !d.isFuture : !d.marked && !d.isFuture));
  }, [calendar, isAdmin]);

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
    setSelectedDates(new Set());
    onNavigate(d.getFullYear(), d.getMonth() + 1);
  }

  const canMark = Boolean(onMark);

  function toggleDate(dateStr: string) {
    setSelectedDates((prev) => {
      const next = new Set(prev);
      if (next.has(dateStr)) next.delete(dateStr);
      else next.add(dateStr);
      return next;
    });
  }

  function selectAllMissing() {
    setSelectedDates(new Set(missingDays.map((d) => d.date)));
  }

  function clearSelection() {
    setSelectedDates(new Set());
    setMultiCount("");
    setCustomCounts({});
  }

  function pick(d: CalendarDay) {
    if (onPickDay) {
      onPickDay(d);
      return;
    }
    if (multiMode) {
      const isSelectable = isAdmin ? !d.isFuture : !d.marked && !d.isFuture;
      if (isSelectable) toggleDate(d.date);
      return;
    }
    if (d.isFuture) return;
    if (d.marked) {
      if (!onCorrect || isAdmin || d.source !== "employee") return;     // only the person who marked a day can change it (admins use their own path)
      setSelected(d);
      setCount(String(d.count ?? ""));
      return;
    }
    if (!onMark) return;
    setSelected(d);
    setCount("");
  }

  const n = Number(count);
  const valid = count !== "" && Number.isInteger(n) && n >= 0 && n <= MAX_BOTTLES;

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!selected || !valid) return;
    if (selected.marked) {
      if (!onCorrect) return;
      await onCorrect(selected.date, n);
    } else {
      if (!onMark) return;
      await onMark(selected.date, n);
    }
    setSelected(null);
    setCount("");
  }

  async function removeEntry() {
    if (!selected || !selected.marked || !onCorrect) return;
    if (!window.confirm(`Remove the entry for ${selected.date}? The day becomes unmarked and you can mark it again.`)) return;
    await onCorrect(selected.date, null);
    setSelected(null);
    setCount("");
  }

  const sortedSelected = useMemo(() => Array.from(selectedDates).sort(), [selectedDates]);
  const defaultMultiNum = Number(multiCount);
  const isValidCommonMulti = multiCount !== "" && Number.isInteger(defaultMultiNum) && defaultMultiNum >= 0 && defaultMultiNum <= MAX_BOTTLES;

  const canSubmitMulti = useMemo(() => {
    if (selectedDates.size === 0 || !onMarkMany) return false;
    if (!customizeEach) return isValidCommonMulti;
    return sortedSelected.every((d) => {
      const c = Number(customCounts[d] ?? multiCount);
      return Number.isInteger(c) && c >= 0 && c <= MAX_BOTTLES;
    });
  }, [selectedDates.size, onMarkMany, customizeEach, isValidCommonMulti, sortedSelected, customCounts, multiCount]);

  async function submitMulti(e: FormEvent) {
    e.preventDefault();
    if (!canSubmitMulti || !onMarkMany) return;
    const entries = sortedSelected.map((d) => ({
      orderDate: d,
      bottleCount: customizeEach ? Number(customCounts[d] ?? multiCount) : defaultMultiNum,
    }));
    await onMarkMany(entries);
    clearSelection();
    setMultiMode(false);
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

        <div className="flex items-center gap-3">
          {canMark && onMarkMany && (missingDays.length > 0 || isAdmin) && (
            <button
              type="button"
              onClick={() => {
                setMultiMode((m) => !m);
                setSelected(null);
                if (multiMode) clearSelection();
              }}
              className={`inline-flex items-center gap-1.5 rounded-xl px-3 py-1.5 text-xs font-bold transition-all ${
                multiMode
                  ? "bg-brand-600 text-white shadow-xs"
                  : "bg-brand-50 text-brand-700 hover:bg-brand-100"
              }`}
            >
              <span>⚡</span>
              {multiMode ? `Multi-date mode (${selectedDates.size})` : "Select multiple dates"}
            </button>
          )}
          <div className="hidden sm:flex gap-3 text-xs text-gray-500">
            <span className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-sm bg-status-success" /> Employee</span>
            <span className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-sm bg-status-warning" /> Admin</span>
            <span className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-sm border border-dashed border-gray-400" /> Missing</span>
          </div>
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
        {multiMode && (
          <div className="mb-4 flex flex-wrap items-center justify-between gap-2 rounded-xl border border-brand-200 bg-brand-50/70 p-3 text-xs">
            <div className="flex items-center gap-2">
              <span className="font-extrabold text-brand-900">
                {selectedDates.size === 0
                  ? "Tap any dates below to select them"
                  : `${selectedDates.size} date${selectedDates.size === 1 ? "" : "s"} selected`}
              </span>
              {selectedDates.size > 0 && (
                <button
                  type="button"
                  onClick={clearSelection}
                  className="font-semibold text-brand-600 hover:underline"
                >
                  Clear
                </button>
              )}
            </div>
            <div className="flex items-center gap-2">
              {missingDays.length > 0 && (
                <button
                  type="button"
                  onClick={selectAllMissing}
                  className="rounded-lg border border-brand-200 bg-white px-2.5 py-1 font-bold text-brand-700 shadow-2xs hover:bg-brand-50"
                >
                  Select all missing ({missingDays.length})
                </button>
              )}
              <button
                type="button"
                onClick={() => {
                  setMultiMode(false);
                  clearSelection();
                }}
                className="font-medium text-gray-500 hover:text-gray-700"
              >
                Single date mode
              </button>
            </div>
          </div>
        )}

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
            const isClickable =
              Boolean(onPickDay) ||
              (canMark && (isAdmin ? !d.isFuture : !d.marked && !d.isFuture)) ||
              (Boolean(onCorrect) && !isAdmin && d.marked && d.source === "employee" && !d.isFuture);
            const isSel = selected?.date === d.date;
            const isPicked = selectedDates.has(d.date);

            return (
              <button
                key={d.day}
                type="button"
                onClick={() => pick(d)}
                disabled={!isClickable}
                title={d.masked ? "Marked by a colleague. This number is not shown to you." : d.marked ? `${d.count} bottles · entered by ${d.enteredBy ?? d.source ?? "unknown"}${d.enteredAt ? ` on ${new Date(d.enteredAt).toLocaleDateString(undefined, { day: "numeric", month: "short" })}` : ""}${d.changed ? ` · changed by ${d.changed.byName ?? "a senior colleague"} (${d.changed.byRoleLabel}), ${d.changed.oldCount} to ${d.changed.newCount}` : ""}${d.verification ? ` · ${d.verification.label}` : ""}` : d.isFuture ? undefined : "Not marked"}
                style={
                  !isPicked && d.marked && !d.masked && d.source !== "admin"
                    ? { backgroundColor: `rgb(var(--success) / ${0.1 + 0.3 * ((d.count ?? 0) / maxCount)})` }
                    : undefined
                }
                className={`relative flex h-14 flex-col sm:h-[4.25rem] items-center justify-center rounded-lg border text-sm transition-[transform,box-shadow,background-color,border-color] disabled:cursor-default ${
                  isPicked
                    ? "ring-2 ring-brand-500 bg-brand-100/70 border-brand-500 text-brand-900 font-extrabold scale-[1.04] shadow-xs z-10"
                    : dayTone(d, isClickable)
                } ${d.isToday ? "ring-2 ring-brand-400 ring-offset-1" : ""} ${
                  isSel ? "scale-[1.04] border-brand-500 bg-brand-50 text-brand-700 shadow-md" : ""
                }`}
              >
                <span className={`absolute left-1.5 top-1 text-[10px] font-semibold ${d.marked ? "opacity-70" : ""}`}>{d.day}</span>
                {d.masked ? (
                  <span className="text-xs font-semibold" aria-label="Marked by a colleague">Marked</span>
                ) : d.marked ? (
                  <span className="text-base font-bold tabular-nums">{d.count}</span>
                ) : !d.isFuture ? (
                  <span className="text-lg font-light text-gray-300">+</span>
                ) : null}
                {d.changed && !d.masked && !isPicked && (
                  <span className="absolute bottom-1 right-1.5 h-2 w-2 rounded-full bg-status-warning" aria-label={`Changed by ${d.changed.byName ?? "a senior colleague"}`} />
                )}
                {isPicked && (
                  <span className="absolute right-1 top-1 flex h-4 w-4 items-center justify-center rounded-full bg-brand-600 text-[10px] text-white font-bold">
                    ✓
                  </span>
                )}
              </button>
            );
          })}
        </div>

        {/* Single date mark form */}
        {!multiMode && selected && (onMark || (selected.marked && onCorrect)) && (
          <form onSubmit={submit} className="mt-5 flex flex-wrap items-end gap-3 rounded-lg border border-brand-100 bg-brand-50/60 p-3.5">
            <div className="min-w-[10rem] flex-1">
              <Input
                label={selected.marked ? `Correct the bottles for ${selected.date} (entered as ${selected.count ?? 0})` : `Bottles for ${selected.date}`}
                type="number"
                inputMode="numeric"
                min={0}
                max={MAX_BOTTLES}
                value={count}
                onChange={(e) => setCount(e.target.value)}
                autoFocus
                hint={`0–${MAX_BOTTLES}. Zero is a valid count.`}
              />
            </div>
            <Button type="submit" isLoading={marking} disabled={!valid}>
              {selected.marked ? "Save correction" : "Save entry"}
            </Button>
            {selected.marked && (
              <Button type="button" variant="secondary" onClick={() => void removeEntry()} disabled={marking}>
                Remove entry
              </Button>
            )}
            <Button type="button" variant="ghost" onClick={() => setSelected(null)} disabled={marking}>
              Cancel
            </Button>
            {onMarkMany && missingDays.length > 1 && (
              <button
                type="button"
                onClick={() => {
                  setMultiMode(true);
                  setSelectedDates(new Set([selected.date]));
                  setSelected(null);
                }}
                className="text-xs font-bold text-brand-600 hover:underline ml-2"
              >
                Select more dates together →
              </button>
            )}
          </form>
        )}

        {/* Multi-date batch entry card */}
        {multiMode && selectedDates.size > 0 && onMarkMany && (
          <form onSubmit={submitMulti} className="mt-5 rounded-2xl border border-brand-200 bg-brand-50/70 p-4 shadow-sm space-y-4">
            <div className="flex flex-wrap items-center justify-between gap-2 border-b border-brand-100 pb-3">
              <div>
                <h4 className="text-sm font-extrabold text-brand-950">
                  Mark {selectedDates.size} Selected Dates Together
                </h4>
                <p className="text-xs text-brand-700">
                  Enter bottle count to log for all selected dates in a single request.
                </p>
              </div>
              <label className="flex items-center gap-1.5 text-xs font-bold text-brand-800 cursor-pointer">
                <input
                  type="checkbox"
                  checked={customizeEach}
                  onChange={(e) => setCustomizeEach(e.target.checked)}
                  className="rounded border-brand-300 text-brand-600 focus:ring-brand-500"
                />
                Customize count per date
              </label>
            </div>

            {!customizeEach ? (
              <div className="space-y-3">
                <div className="flex flex-wrap items-center gap-3">
                  <div className="w-40">
                    <Input
                      label="Bottles count"
                      type="number"
                      inputMode="numeric"
                      min={0}
                      max={MAX_BOTTLES}
                      value={multiCount}
                      onChange={(e) => setMultiCount(e.target.value)}
                      autoFocus
                      placeholder="e.g. 15"
                      hint={`0–${MAX_BOTTLES}`}
                    />
                  </div>
                  <div className="flex flex-wrap items-center gap-1.5 pt-2">
                    {[0, 5, 10, 15, 20, 25, 30].map((preset) => (
                      <button
                        key={preset}
                        type="button"
                        onClick={() => setMultiCount(String(preset))}
                        className={`rounded-lg px-2.5 py-1.5 text-xs font-bold border transition-colors ${
                          multiCount === String(preset)
                            ? "border-brand-600 bg-brand-600 text-white"
                            : "border-brand-200 bg-white text-brand-800 hover:bg-brand-100"
                        }`}
                      >
                        {preset === 0 ? "0 (Closed)" : `${preset} bottles`}
                      </button>
                    ))}
                  </div>
                </div>
              </div>
            ) : (
              <div className="grid gap-2 sm:grid-cols-2 max-h-48 overflow-y-auto pr-1">
                {sortedSelected.map((d) => (
                  <div key={d} className="flex items-center justify-between rounded-xl bg-white p-2.5 border border-brand-100">
                    <span className="text-xs font-bold text-gray-800">{d}</span>
                    <input
                      type="number"
                      inputMode="numeric"
                      min={0}
                      max={MAX_BOTTLES}
                      value={customCounts[d] ?? multiCount}
                      onChange={(e) => setCustomCounts((prev) => ({ ...prev, [d]: e.target.value }))}
                      placeholder={multiCount || "0"}
                      className="h-8 w-20 rounded-lg border border-surface-border text-center text-xs font-bold focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20 outline-none"
                    />
                  </div>
                ))}
              </div>
            )}

            <div className="flex flex-wrap items-center justify-between gap-3 pt-2 border-t border-brand-100">
              <span className="text-xs text-brand-700">
                Selected: <b className="font-semibold">{sortedSelected.map((d) => d.slice(5)).join(", ")}</b>
              </span>
              <div className="flex items-center gap-2">
                <Button type="button" variant="ghost" size="sm" onClick={clearSelection} disabled={marking}>
                  Cancel
                </Button>
                <Button type="submit" size="sm" isLoading={marking} disabled={!canSubmitMulti}>
                  Save All {selectedDates.size} Orders
                </Button>
              </div>
            </div>
          </form>
        )}

        {!isAdmin && <ChangedByList days={calendar.days} />}

        {!multiMode && !selected && canMark && stats.missing > 0 && (
          <div className="mt-4 flex flex-wrap items-center justify-center gap-2 text-xs text-gray-500">
            <span>Tap a dashed day to add its bottle count, or</span>
            <button
              type="button"
              onClick={() => setMultiMode(true)}
              className="font-bold text-brand-600 hover:underline"
            >
              switch to multi-date select
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
