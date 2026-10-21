import { useMemo, useState, type FormEvent } from "react";
import { MAX_BOTTLES } from "@/features/orders/limits";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { useCalendar, useMarkManyOrders } from "@/features/orders/useOrders";
import type { MyStore } from "@/types/order";

const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

interface Props {
  isOpen: boolean;
  onClose: () => void;
  stores: MyStore[];
  initialStoreId?: string;
  isAdmin?: boolean;
}

export function MultiDateMarkModal({
  isOpen,
  onClose,
  stores,
  initialStoreId,
  isAdmin,
}: Props) {
  const [storeId, setStoreId] = useState(initialStoreId || stores[0]?.id || "");
  const [selectedDates, setSelectedDates] = useState<Set<string>>(new Set());
  const [count, setCount] = useState("");
  const [customCounts, setCustomCounts] = useState<Record<string, string>>({});
  const [customizeEach, setCustomizeEach] = useState(false);

  const markMany = useMarkManyOrders();

  const { data: calendar, isLoading: calLoading } = useCalendar(storeId || null);

  const missingDays = useMemo(() => {
    if (!calendar) return [];
    return calendar.days.filter((d) => (isAdmin ? !d.isFuture : !d.marked && !d.isFuture));
  }, [calendar, isAdmin]);

  const firstWeekday = calendar ? new Date(calendar.year, calendar.month - 1, 1).getDay() : 0;
  const blanks = Array.from({ length: firstWeekday });

  function toggleDate(dStr: string) {
    setSelectedDates((prev) => {
      const next = new Set(prev);
      if (next.has(dStr)) next.delete(dStr);
      else next.add(dStr);
      return next;
    });
  }

  function selectAllMissing() {
    setSelectedDates(new Set(missingDays.map((d) => d.date)));
  }

  function selectLastNDays(n: number) {
    const sorted = [...missingDays].sort((a, b) => b.day - a.day);
    const slice = sorted.slice(0, n);
    setSelectedDates(new Set(slice.map((d) => d.date)));
  }

  function clearSelection() {
    setSelectedDates(new Set());
  }

  const sortedSelected = useMemo(
    () => Array.from(selectedDates).sort(),
    [selectedDates],
  );

  const defaultNum = Number(count);
  const isValidCommon = count !== "" && Number.isInteger(defaultNum) && defaultNum >= 0 && defaultNum <= MAX_BOTTLES;

  const canSubmit = useMemo(() => {
    if (selectedDates.size === 0) return false;
    if (!customizeEach) return isValidCommon;
    return sortedSelected.every((d) => {
      const c = Number(customCounts[d] ?? count);
      return Number.isInteger(c) && c >= 0 && c <= MAX_BOTTLES;
    });
  }, [selectedDates.size, customizeEach, isValidCommon, sortedSelected, customCounts, count]);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!canSubmit || !storeId) return;

    const entries = sortedSelected.map((d) => ({
      orderDate: d,
      bottleCount: customizeEach ? Number(customCounts[d] ?? count) : defaultNum,
    }));

    await markMany.mutateAsync({ storeId, entries });
    clearSelection();
    setCount("");
    setCustomCounts({});
    onClose();
  }

  if (!isOpen) return null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="multi-date-modal-title"
      className="fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-6"
    >
      <div className="fixed inset-0 bg-black/50 backdrop-blur-xs transition-opacity" onClick={onClose} />

      <div className="relative flex max-h-[92vh] w-full max-w-2xl flex-col overflow-hidden rounded-2xl border border-surface-border bg-surface shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-surface-border px-6 py-4">
          <div className="flex items-center gap-2.5">
            <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-brand-50 text-brand-600 font-bold text-sm">
              ⚡
            </span>
            <div>
              <h2 id="multi-date-modal-title" className="text-base font-extrabold text-heading">
                Mark Multiple Dates Together
              </h2>
              <p className="text-xs text-gray-500">
                Select multiple dates for a store and log all bottle counts in one batch.
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close dialog"
            className="rounded-lg p-1 text-gray-400 hover:bg-surface-muted hover:text-gray-700"
          >
            ✕
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto px-6 py-5 space-y-5">
          {/* 1. Store selector */}
          <div>
            <Select
              label="1. Choose Store"
              id="multi-store-select"
              value={storeId}
              onChange={(e) => {
                setStoreId(e.target.value);
                setSelectedDates(new Set());
              }}
              options={stores.map((s) => ({
                value: s.id,
                label: `${s.name} (${s.externalCode})${s.partnerName ? ` · ${s.partnerName}` : ""}`,
              }))}
              className="w-full"
            />
          </div>

          {/* 2. Date selection */}
          <div>
            <div className="flex flex-wrap items-center justify-between gap-2 mb-2">
              <label className="text-xs font-bold text-gray-700 uppercase tracking-wider">
                2. Select Dates ({selectedDates.size} selected)
              </label>
              <div className="flex items-center gap-1.5">
                {missingDays.length > 0 && (
                  <>
                    <button
                      type="button"
                      onClick={() => selectLastNDays(2)}
                      className="rounded-md border border-gray-200 bg-surface px-2 py-0.5 text-xs font-semibold text-gray-600 hover:bg-surface-subtle"
                    >
                      Last 2 days
                    </button>
                    <button
                      type="button"
                      onClick={() => selectLastNDays(7)}
                      className="rounded-md border border-gray-200 bg-surface px-2 py-0.5 text-xs font-semibold text-gray-600 hover:bg-surface-subtle"
                    >
                      Last 7 days
                    </button>
                    <button
                      type="button"
                      onClick={selectAllMissing}
                      className="rounded-md bg-brand-50 px-2 py-0.5 text-xs font-bold text-brand-700 hover:bg-brand-100"
                    >
                      All missing ({missingDays.length})
                    </button>
                  </>
                )}
                {selectedDates.size > 0 && (
                  <button
                    type="button"
                    onClick={clearSelection}
                    className="text-xs font-semibold text-brand-600 hover:underline ml-1"
                  >
                    Clear
                  </button>
                )}
              </div>
            </div>

            {calLoading && (
              <div className="h-48 animate-pulse rounded-xl bg-surface-subtle border border-surface-border" />
            )}

            {calendar && (
              <div className="rounded-xl border border-surface-border bg-surface-subtle/50 p-3">
                <div className="text-center font-bold text-sm text-heading mb-2">
                  {calendar.monthLabel}
                </div>
                <div className="grid grid-cols-7 gap-1 text-center text-[10px] font-bold text-gray-400 mb-1">
                  {WEEKDAYS.map((w) => (
                    <div key={w}>{w}</div>
                  ))}
                </div>
                <div className="grid grid-cols-7 gap-1">
                  {blanks.map((_, i) => (
                    <div key={`b-${i}`} />
                  ))}
                  {calendar.days.map((d) => {
                    const isSelectable = isAdmin ? !d.isFuture : !d.marked && !d.isFuture;
                    const isPicked = selectedDates.has(d.date);

                    return (
                      <button
                        key={d.day}
                        type="button"
                        disabled={!isSelectable}
                        onClick={() => toggleDate(d.date)}
                        title={d.marked ? `Already marked: ${d.count}` : d.isFuture ? "Future date" : d.date}
                        className={`relative flex h-10 flex-col items-center justify-center rounded-lg border text-xs font-bold transition-all ${
                          isPicked
                            ? "border-brand-600 bg-brand-600 text-white shadow-xs scale-105 z-10"
                            : d.marked
                              ? "border-status-success/30 bg-status-success-soft text-status-success cursor-not-allowed opacity-75"
                              : d.isFuture
                                ? "border-transparent bg-transparent text-gray-300 cursor-not-allowed"
                                : "border-dashed border-gray-300 bg-surface text-gray-700 hover:border-brand-500 hover:bg-brand-50"
                        }`}
                      >
                        <span>{d.day}</span>
                        {d.marked && <span className="text-[9px] font-normal leading-none">{d.count}b</span>}
                        {isPicked && (
                          <span className="absolute top-0.5 right-1 text-[8px] leading-none">✓</span>
                        )}
                      </button>
                    );
                  })}
                </div>
              </div>
            )}
          </div>

          {/* 3. Bottle count */}
          {selectedDates.size > 0 && (
            <div className="rounded-xl border border-brand-100 bg-brand-50/50 p-4 space-y-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <label htmlFor="multi-bottle-input" className="text-xs font-bold text-brand-900 uppercase tracking-wider">
                  3. Bottle Count (0–{MAX_BOTTLES})
                </label>
                <label className="flex items-center gap-1.5 text-xs font-semibold text-brand-700 cursor-pointer">
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
                <div>
                  <div className="flex items-end gap-3">
                    <div className="w-36">
                      <Input
                        label="Bottles count"
                        id="multi-bottle-input"
                        type="number"
                        inputMode="numeric"
                        min={0}
                        max={MAX_BOTTLES}
                        value={count}
                        onChange={(e) => setCount(e.target.value)}
                        placeholder="e.g. 15"
                        className="text-center font-bold text-base"
                      />
                    </div>
                    <span className="pb-2 text-xs text-gray-500">applied to all {selectedDates.size} dates</span>
                  </div>
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {[0, 5, 10, 15, 20, 25, 30].map((preset) => (
                      <button
                        key={preset}
                        type="button"
                        onClick={() => setCount(String(preset))}
                        className={`rounded-md px-2.5 py-1 text-xs font-semibold border transition-colors ${
                          count === String(preset)
                            ? "border-brand-600 bg-brand-600 text-white"
                            : "border-brand-200 bg-white text-brand-800 hover:bg-brand-50"
                        }`}
                      >
                        {preset === 0 ? "0 (Closed)" : `${preset} bottles`}
                      </button>
                    ))}
                  </div>
                </div>
              ) : (
                <div className="max-h-40 overflow-y-auto space-y-1.5 pr-1">
                  {sortedSelected.map((d) => (
                    <div key={d} className="flex items-center justify-between rounded-lg bg-white p-2 border border-brand-100">
                      <span className="text-xs font-bold text-gray-700">{d}</span>
                      <input
                        type="number"
                        inputMode="numeric"
                        min={0}
                        max={MAX_BOTTLES}
                        value={customCounts[d] ?? count}
                        onChange={(e) =>
                          setCustomCounts((prev) => ({ ...prev, [d]: e.target.value }))
                        }
                        placeholder={count || "0"}
                        className="h-8 w-20 rounded-md border border-surface-border text-center text-xs font-bold"
                      />
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between border-t border-surface-border bg-surface-subtle/50 px-6 py-4">
          <p className="text-xs text-gray-500">
            {selectedDates.size > 0
              ? `Ready to mark ${selectedDates.size} order${selectedDates.size === 1 ? "" : "s"}`
              : "Select dates above to proceed"}
          </p>
          <div className="flex items-center gap-2">
            <Button type="button" variant="ghost" onClick={onClose} disabled={markMany.isPending}>
              Cancel
            </Button>
            <Button
              type="button"
              onClick={handleSubmit}
              disabled={!canSubmit}
              isLoading={markMany.isPending}
            >
              Mark {selectedDates.size || 0} Orders Together
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
