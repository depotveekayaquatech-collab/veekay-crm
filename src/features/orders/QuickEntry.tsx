import { useMemo, useRef, useState } from "react";
import { Button } from "@/components/ui/Button";
import { usePermission } from "@/hooks/usePermission";
import { IconCheckCircle, IconMapPin } from "@/components/ui/icons";
import { FilterChip, ProgressBar, ProgressRing, SearchBox, SegmentedControl } from "@/features/orders/ui";
import { useMarkOrder } from "@/features/orders/useOrders";
import type { MyStore } from "@/types/order";

type Day = "today" | "yesterday";
type Show = "todo" | "done" | "all";

const MAX = 200;
const PAGE = 50; // rows drawn at a time — an admin sees every live store, and 1,000+ inputs at once would lag
const HIGH = 100;

function shiftDate(iso: string, days: number): string {
  const d = new Date(`${iso}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

function Row({
  store,
  existing,
  saving,
  suggestion,
  canEdit,
  onSave,
  inputRef,
}: {
  store: MyStore;
  existing: number | null;
  saving: boolean;
  /** Yesterday's count, offered as a one-tap fill for today. */
  suggestion: number | null;
  /** Admins can change a saved count; everyone else's entries are one-shot. */
  canEdit: boolean;
  onSave: (count: number) => void;
  inputRef: (el: HTMLInputElement | null) => void;
}) {
  const [value, setValue] = useState("");
  const [editing, setEditing] = useState(false);
  const n = Number(value);
  const valid = value !== "" && Number.isInteger(n) && n >= 0 && n <= MAX;
  const live = store.status === "LIVE";
  const place = [store.city, store.state].filter(Boolean).join(", ");
  const bump = (by: number) => setValue(String(Math.max(0, Math.min(MAX, (value === "" ? 0 : n) + by))));

  return (
    <li className={`flex flex-wrap items-center gap-x-4 gap-y-3 px-4 py-3.5 transition-colors sm:px-5 ${existing !== null ? "bg-status-success-soft/30" : "hover:bg-surface-subtle/70"}`}>
      <span
        className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-xl ${
          existing !== null ? "bg-status-success text-white" : live ? "bg-surface-muted text-gray-500" : "bg-surface-muted text-gray-400"
        }`}
        aria-hidden="true"
      >
        {existing !== null ? <IconCheckCircle className="h-5 w-5" /> : <IconMapPin className="h-5 w-5" />}
      </span>

      <div className="min-w-0 flex-1 basis-52">
        <p className="truncate text-sm font-bold text-gray-900">{store.name}</p>
        <p className="flex flex-wrap items-center gap-x-2 text-xs text-gray-500">
          <span className="font-medium text-gray-600">{store.externalCode}</span>
          {place && <span>{place}</span>}
          {store.pocNumber && (
            <a href={`tel:${store.pocNumber}`} className="font-medium text-brand-600 hover:text-brand-700">
              {store.pocNumber}
            </a>
          )}
        </p>
      </div>

      {existing !== null && !editing ? (
        <div className="flex items-center gap-2">
          <div className="flex items-baseline gap-1.5 rounded-xl bg-status-success-soft px-3.5 py-2 text-status-success">
            <span className="text-xl font-extrabold tabular-nums">{existing}</span>
            <span className="text-xs font-semibold">bottles · saved</span>
          </div>
          {canEdit && (
            <Button
              type="button"
              variant="secondary"
              size="sm"
              onClick={() => {
                setValue(String(existing));
                setEditing(true);
              }}
            >
              Edit
            </Button>
          )}
        </div>
      ) : !live ? (
        <span className="rounded-full bg-surface-muted px-3 py-1 text-xs font-semibold text-gray-500">Not live</span>
      ) : (
        <form
          className="flex flex-wrap items-center gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            if (valid && !saving) {
              onSave(n);
              setEditing(false);
            }
          }}
        >
          {suggestion !== null && value === "" && (
            <button
              type="button"
              onClick={() => setValue(String(suggestion))}
              className="rounded-full border border-dashed border-brand-500/50 px-2.5 py-1 text-xs font-semibold text-brand-600 hover:bg-brand-50"
              title="Fill in yesterday's count"
            >
              Same as yesterday · {suggestion}
            </button>
          )}
          <div className="flex items-center overflow-hidden rounded-xl border border-surface-border bg-surface shadow-sm focus-within:border-brand-500 focus-within:ring-2 focus-within:ring-brand-500/20">
            <button type="button" onClick={() => bump(-1)} aria-label={`Decrease count for ${store.name}`} className="h-10 w-9 text-lg font-semibold text-gray-500 hover:bg-surface-muted hover:text-gray-900">
              −
            </button>
            <input
              ref={inputRef}
              type="number"
              inputMode="numeric"
              min={0}
              max={MAX}
              value={value}
              onChange={(e) => setValue(e.target.value)}
              aria-label={`Bottle count for ${store.name}`}
              placeholder="0"
              className="h-10 w-16 border-x border-surface-border bg-transparent text-center text-sm font-bold tabular-nums outline-none [appearance:textfield] placeholder:text-gray-300 [&::-webkit-inner-spin-button]:appearance-none [&::-webkit-outer-spin-button]:appearance-none"
            />
            <button type="button" onClick={() => bump(1)} aria-label={`Increase count for ${store.name}`} className="h-10 w-9 text-lg font-semibold text-gray-500 hover:bg-surface-muted hover:text-gray-900">
              +
            </button>
          </div>
          <Button type="submit" disabled={!valid} isLoading={saving}>
            {editing ? "Update" : "Save"}
          </Button>
          {editing && (
            <Button type="button" variant="ghost" onClick={() => setEditing(false)}>
              Cancel
            </Button>
          )}
          {valid && n >= HIGH && <p className="basis-full text-xs font-medium text-status-warning">That's a high count — double-check before saving.</p>}
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
  const canCorrect = usePermission("orders.correct");
  const [day, setDay] = useState<Day>("today");
  const [query, setQuery] = useState("");
  const [show, setShow] = useState<Show>("todo");
  const [savingId, setSavingId] = useState<string | null>(null);
  const inputs = useRef(new Map<string, HTMLInputElement | null>());

  const today = stores[0]?.today ?? "";
  const yesterday = today ? shiftDate(today, -1) : "";
  // Employees can only mark inside the current month, so "Yesterday" is unavailable on the 1st (admins have no such limit).
  const yesterdayAllowed = Boolean(today) && (canCorrect || yesterday.slice(0, 7) === today.slice(0, 7));
  const activeDay: Day = day === "yesterday" && yesterdayAllowed ? "yesterday" : "today";
  const date = activeDay === "today" ? today : yesterday;

  const countOf = (s: MyStore) => (activeDay === "today" ? s.todayCount : s.yesterdayCount);

  const liveStores = useMemo(() => stores.filter((s) => s.status === "LIVE"), [stores]);
  const done = liveStores.filter((s) => countOf(s) !== null).length;
  const todo = liveStores.length - done;
  const bottles = liveStores.reduce((sum, s) => sum + (countOf(s) ?? 0), 0);
  const percent = liveStores.length ? Math.round((done / liveStores.length) * 100) : 0;

  const rows = useMemo(() => {
    const q = query.trim().toLowerCase();
    const isOpen = (s: MyStore) => s.status === "LIVE" && countOf(s) === null;
    return stores
      .filter((s) => !q || [s.name, s.externalCode, s.city, s.state].some((f) => (f ?? "").toLowerCase().includes(q)))
      .filter((s) => (show === "todo" ? isOpen(s) : show === "done" ? countOf(s) !== null : true))
      .sort((a, b) => Number(!(a.status === "LIVE" && countOf(a) === null)) - Number(!(b.status === "LIVE" && countOf(b) === null)) || a.name.localeCompare(b.name));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stores, query, show, activeDay]);

  // How many rows to draw; resets to one page whenever the search / filter / day changes.
  const viewKey = `${query}|${show}|${activeDay}`;
  const [more, setMore] = useState({ key: viewKey, n: PAGE });
  const shown = more.key === viewKey ? more.n : PAGE;

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
    <section className="flex flex-col gap-5">
      <div className="relative overflow-hidden rounded-2xl border border-surface-border bg-surface p-4 shadow-card sm:p-6">
        <span aria-hidden="true" className="pointer-events-none absolute -left-10 -top-16 h-48 w-48 rounded-full bg-gradient-to-br from-aqua-400/15 to-transparent blur-2xl" />
        <div className="relative flex flex-wrap items-center gap-x-8 gap-y-5">
          <ProgressRing percent={percent} sublabel="marked" />
          <div className="min-w-[14rem] flex-1">
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
              <span className="text-sm font-medium text-gray-500">{date}</span>
            </div>
            <div className="mt-4 grid grid-cols-3 gap-4">
              <div>
                <p className="text-[11px] font-bold uppercase tracking-wider text-gray-500">Marked</p>
                <p className="text-2xl font-extrabold tabular-nums text-heading">{done}<span className="text-base font-semibold text-gray-400"> / {liveStores.length}</span></p>
              </div>
              <div>
                <p className="text-[11px] font-bold uppercase tracking-wider text-gray-500">To go</p>
                <p className={`text-2xl font-extrabold tabular-nums ${todo ? "text-status-warning" : "text-status-success"}`}>{todo}</p>
              </div>
              <div>
                <p className="text-[11px] font-bold uppercase tracking-wider text-gray-500">Bottles</p>
                <p className="text-2xl font-extrabold tabular-nums text-heading">{bottles.toLocaleString()}</p>
              </div>
            </div>
            <ProgressBar percent={percent} className="mt-4" />
          </div>
        </div>
      </div>

      <div className="overflow-hidden rounded-2xl border border-surface-border bg-surface shadow-card">
        <div className="flex flex-wrap items-center gap-3 border-b border-surface-border p-3.5 sm:px-5">
          <SearchBox hotkey value={query} onChange={setQuery} placeholder="Search store, code or city" className="w-full sm:w-72" />
          <div className="flex flex-wrap gap-1.5">
            <FilterChip active={show === "todo"} onClick={() => setShow("todo")} count={todo}>To mark</FilterChip>
            <FilterChip active={show === "done"} onClick={() => setShow("done")} count={done}>Done</FilterChip>
            <FilterChip active={show === "all"} onClick={() => setShow("all")} count={stores.length}>All</FilterChip>
          </div>
          <p className="ml-auto hidden text-xs text-gray-400 lg:block">
            <kbd className="rounded border border-surface-border px-1 font-semibold">Enter</kbd> saves &amp; jumps to the next store · {canCorrect ? "you can edit saved entries" : "saved entries need an admin to change"}
          </p>
        </div>

        {rows.length === 0 ? (
          <div className="flex flex-col items-center gap-2 px-6 py-14 text-center">
            <span className="flex h-14 w-14 items-center justify-center rounded-2xl bg-status-success-soft text-status-success">
              <IconCheckCircle className="h-7 w-7" aria-hidden="true" />
            </span>
            <p className="text-base font-bold text-heading">{query ? "No stores match" : show === "todo" ? "All caught up" : "Nothing here yet"}</p>
            {!query && show === "todo" && (
              <p className="text-sm text-gray-500">
                Every live store has a count for {date} — {bottles.toLocaleString()} bottles in total. Nice work.
              </p>
            )}
          </div>
        ) : (
          <ul className="divide-y divide-surface-border">
            {rows.slice(0, shown).map((s) => (
              <Row
                key={`${s.id}-${date}`}
                store={s}
                existing={countOf(s)}
                saving={savingId === s.id}
                suggestion={activeDay === "today" ? s.yesterdayCount : null}
                canEdit={canCorrect}
                onSave={(c) => void save(s, c)}
                inputRef={(el) => {
                  inputs.current.set(s.id, el);
                }}
              />
            ))}
          </ul>
        )}
        {rows.length > shown && (
          <div className="flex items-center justify-center gap-3 border-t border-surface-border px-4 py-3 text-sm">
            <span className="text-gray-500">Showing {shown} of {rows.length}</span>
            <Button variant="secondary" size="sm" onClick={() => setMore({ key: viewKey, n: shown + PAGE })}>
              Show {Math.min(PAGE, rows.length - shown)} more
            </Button>
          </div>
        )}
      </div>
    </section>
  );
}
