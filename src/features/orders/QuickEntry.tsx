import { useMemo, useRef, useState } from "react";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { IconCheckCircle, IconMapPin } from "@/components/ui/icons";
import { ProgressBar, SearchBox, SegmentedControl } from "@/features/orders/ui";
import { useMarkOrder } from "@/features/orders/useOrders";
import type { MyStore } from "@/types/order";

type Day = "today" | "yesterday";

function shiftDate(iso: string, days: number): string {
  const d = new Date(`${iso}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

function Phone({ value }: { value: string | null }) {
  if (!value) return null;
  return (
    <a href={`tel:${value}`} className="font-medium text-brand-600 hover:text-brand-700">
      {value}
    </a>
  );
}

function Row({
  store,
  existing,
  saving,
  onSave,
  inputRef,
}: {
  store: MyStore;
  existing: number | null;
  saving: boolean;
  onSave: (count: number) => void;
  inputRef: (el: HTMLInputElement | null) => void;
}) {
  const [value, setValue] = useState("");
  const n = Number(value);
  const valid = value !== "" && Number.isInteger(n) && n >= 0 && n <= 200;
  const live = store.status === "LIVE";
  const place = [store.city, store.state].filter(Boolean).join(", ");

  return (
    <li className="flex flex-wrap items-center gap-x-4 gap-y-2 px-4 py-3 sm:px-5">
      <div className="min-w-0 flex-1 basis-56">
        <p className="truncate text-sm font-semibold text-gray-900">{store.name}</p>
        <p className="flex flex-wrap items-center gap-x-2 text-xs text-gray-500">
          <span>{store.externalCode}</span>
          {place && (
            <span className="flex items-center gap-1">
              <IconMapPin className="h-3 w-3" />
              {place}
            </span>
          )}
          {store.pocNumber && <Phone value={store.pocNumber} />}
        </p>
      </div>

      {existing !== null ? (
        <div className="flex items-center gap-2 text-status-success">
          <IconCheckCircle className="h-5 w-5" />
          <span className="text-sm font-bold tabular-nums">{existing}</span>
          <span className="text-xs text-gray-500">bottles</span>
        </div>
      ) : !live ? (
        <Badge tone="neutral">Not live</Badge>
      ) : (
        <form
          className="flex items-center gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            if (valid && !saving) onSave(n);
          }}
        >
          <input
            ref={inputRef}
            type="number"
            inputMode="numeric"
            min={0}
            max={200}
            value={value}
            onChange={(e) => setValue(e.target.value)}
            aria-label={`Bottle count for ${store.name}`}
            placeholder="0–200"
            className="h-10 w-28 rounded-lg border border-surface-border bg-white px-3 text-sm tabular-nums shadow-sm outline-none placeholder:text-gray-400 focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20"
          />
          <Button type="submit" size="md" disabled={!valid} isLoading={saving}>
            Save
          </Button>
        </form>
      )}
    </li>
  );
}

/**
 * The fast path for a normal day: every store on one list, type a count, press Enter, next store.
 * Entries are one-shot for employees, so saving is always an explicit action (Enter or the Save button).
 */
export function QuickEntry({ stores }: { stores: MyStore[] }) {
  const mark = useMarkOrder();
  const [day, setDay] = useState<Day>("today");
  const [query, setQuery] = useState("");
  const [openOnly, setOpenOnly] = useState(true);
  const [savingId, setSavingId] = useState<string | null>(null);
  const inputs = useRef(new Map<string, HTMLInputElement | null>());

  const today = stores[0]?.today ?? "";
  const yesterday = today ? shiftDate(today, -1) : "";
  // Employees can only mark inside the current month, so "Yesterday" is unavailable on the 1st.
  const yesterdayAllowed = Boolean(today) && yesterday.slice(0, 7) === today.slice(0, 7);
  const activeDay: Day = day === "yesterday" && yesterdayAllowed ? "yesterday" : "today";
  const date = activeDay === "today" ? today : yesterday;

  const countOf = (s: MyStore) => (activeDay === "today" ? s.todayCount : s.yesterdayCount);

  const liveStores = useMemo(() => stores.filter((s) => s.status === "LIVE"), [stores]);
  const done = liveStores.filter((s) => countOf(s) !== null).length;
  const bottles = liveStores.reduce((sum, s) => sum + (countOf(s) ?? 0), 0);
  const percent = liveStores.length ? Math.round((done / liveStores.length) * 100) : 0;

  const rows = useMemo(() => {
    const q = query.trim().toLowerCase();
    return stores
      .filter((s) => !q || [s.name, s.externalCode, s.city, s.state].some((f) => (f ?? "").toLowerCase().includes(q)))
      .filter((s) => !openOnly || (s.status === "LIVE" && countOf(s) === null))
      .sort((a, b) => a.name.localeCompare(b.name));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stores, query, openOnly, activeDay]);

  async function save(store: MyStore, count: number) {
    setSavingId(store.id);
    try {
      await mark.mutateAsync({ storeId: store.id, date, count });
      // Jump to the next store that still needs a number.
      const next = rows.find((r) => r.id !== store.id && r.status === "LIVE" && countOf(r) === null);
      if (next) setTimeout(() => inputs.current.get(next.id)?.focus(), 50);
    } finally {
      setSavingId(null);
    }
  }

  return (
    <section className="overflow-hidden rounded-xl border border-surface-border bg-white shadow-card">
      <div className="flex flex-col gap-3 border-b border-surface-border p-4 sm:p-5">
        <div className="flex flex-wrap items-center gap-3">
          <SegmentedControl
            label="Day"
            value={activeDay}
            onChange={setDay}
            options={[
              { value: "today", label: "Today" },
              ...(yesterdayAllowed ? [{ value: "yesterday" as const, label: "Yesterday" }] : []),
            ]}
          />
          <p className="text-sm text-gray-500">
            {date} · <span className="font-semibold text-gray-800">{done}</span> of {liveStores.length} stores marked ·{" "}
            <span className="font-semibold text-gray-800">{bottles.toLocaleString()}</span> bottles
          </p>
        </div>
        <ProgressBar percent={percent} />
        <div className="flex flex-wrap items-center gap-3">
          <SearchBox value={query} onChange={setQuery} placeholder="Search store, code or city" className="w-full sm:w-72" />
          <label className="flex cursor-pointer items-center gap-2 text-sm text-gray-600">
            <input type="checkbox" checked={openOnly} onChange={(e) => setOpenOnly(e.target.checked)} className="accent-brand-500" />
            Show only stores still to mark
          </label>
          <span className="ml-auto text-xs text-gray-400">Saved entries can't be changed — ask an admin to correct a mistake.</span>
        </div>
      </div>

      {rows.length === 0 ? (
        <div className="flex flex-col items-center gap-2 px-6 py-14 text-center">
          <span className="flex h-12 w-12 items-center justify-center rounded-full bg-status-success-soft text-status-success">
            <IconCheckCircle className="h-6 w-6" />
          </span>
          <p className="text-base font-bold text-ink-900">{query ? "No stores match" : "All caught up"}</p>
          {!query && <p className="text-sm text-gray-500">Every live store has a count for {date}.</p>}
        </div>
      ) : (
        <ul className="divide-y divide-surface-border">
          {rows.map((s) => (
            <Row
              key={`${s.id}-${date}`}
              store={s}
              existing={countOf(s)}
              saving={savingId === s.id}
              onSave={(c) => void save(s, c)}
              inputRef={(el) => {
                inputs.current.set(s.id, el);
              }}
            />
          ))}
        </ul>
      )}
    </section>
  );
}
