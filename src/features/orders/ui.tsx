import { useMemo, useState, type ReactNode } from "react";
import { IconSearch, IconStore } from "@/components/ui/icons";
import { Select } from "@/components/ui/Select";
import type { Option } from "@/lib/options";

/** Small building blocks shared by every tab of the Orders section, so they all look and behave alike. */

export function SegmentedControl<T extends string>({
  options,
  value,
  onChange,
  label,
}: {
  options: { value: T; label: string }[];
  value: T;
  onChange: (v: T) => void;
  label: string;
}) {
  return (
    <div role="tablist" aria-label={label} className="inline-flex max-w-full gap-1 overflow-x-auto rounded-lg bg-surface-muted p-1">
      {options.map((o) => (
        <button
          key={o.value}
          role="tab"
          aria-selected={value === o.value}
          onClick={() => onChange(o.value)}
          className={`whitespace-nowrap rounded-md px-3.5 py-1.5 text-sm font-medium transition-all ${
            value === o.value ? "bg-white text-brand-700 shadow-sm" : "text-gray-500 hover:text-gray-800"
          }`}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

export function SearchBox({
  value,
  onChange,
  placeholder,
  className = "",
}: {
  value: string;
  onChange: (v: string) => void;
  placeholder: string;
  className?: string;
}) {
  return (
    <div className={`relative ${className}`}>
      <IconSearch className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" />
      <input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        aria-label={placeholder}
        className="h-10 w-full rounded-lg border border-surface-border bg-white pl-9 pr-3 text-sm shadow-sm outline-none placeholder:text-gray-400 focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20"
      />
    </div>
  );
}

export function ProgressBar({ percent, className = "" }: { percent: number; className?: string }) {
  const p = Math.max(0, Math.min(100, percent));
  const tone = p >= 85 ? "bg-status-success" : p >= 50 ? "bg-brand-500" : "bg-status-warning";
  return (
    <div className={`h-1.5 overflow-hidden rounded-full bg-surface-muted ${className}`} role="progressbar" aria-valuenow={p} aria-valuemin={0} aria-valuemax={100}>
      <div className={`h-full rounded-full transition-all ${tone}`} style={{ width: `${p}%` }} />
    </div>
  );
}

const TILE_TONE = { brand: "tile-brand", aqua: "tile-aqua", success: "tile-success", warning: "tile-warning" } as const;

export function StatCard({
  label,
  value,
  hint,
  tone = "brand",
  valueClassName = "text-ink-900",
  children,
}: {
  label: string;
  value: ReactNode;
  hint?: ReactNode;
  tone?: keyof typeof TILE_TONE;
  valueClassName?: string;
  children?: ReactNode;
}) {
  return (
    <div className={`tile ${TILE_TONE[tone]} rounded-xl border border-surface-border bg-white p-4 shadow-card`}>
      <p className="text-[11px] font-bold uppercase tracking-wider text-gray-500">{label}</p>
      <p className={`mt-1.5 text-[1.65rem] font-bold leading-none tabular-nums ${valueClassName}`}>{value}</p>
      {hint && <p className="mt-1.5 text-xs text-gray-500">{hint}</p>}
      {children}
    </div>
  );
}

export function Avatar({ name }: { name: string }) {
  const parts = name.trim().split(/\s+/);
  const text = ((parts[0]?.[0] ?? "") + (parts[1]?.[0] ?? "")).toUpperCase() || "?";
  return (
    <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-brand-50 text-[11px] font-bold text-brand-700 ring-1 ring-brand-100">
      {text}
    </span>
  );
}

export interface PickableStore {
  id: string;
  name: string;
  externalCode: string;
  city?: string | null;
  state?: string | null;
  partnerName?: string | null;
}

/** Searchable store list — click a store to select it. Used by both "Mark orders" and "Correct entries". */
export function StorePicker({
  stores,
  selectedId,
  onSelect,
  title = "Stores",
  filters,
}: {
  stores: PickableStore[];
  selectedId: string;
  onSelect: (id: string) => void;
  title?: string;
  filters?: ReactNode;
}) {
  const [query, setQuery] = useState("");
  const visible = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return stores;
    return stores.filter((s) => [s.name, s.externalCode, s.city, s.state].some((f) => (f ?? "").toLowerCase().includes(q)));
  }, [stores, query]);

  return (
    <div className="flex flex-col overflow-hidden rounded-xl border border-surface-border bg-white shadow-card lg:sticky lg:top-24 lg:max-h-[calc(100vh-7.5rem)]">
      <div className="flex shrink-0 flex-col gap-3 border-b border-surface-border p-3.5">
        <div className="flex items-center justify-between">
          <p className="text-sm font-semibold text-ink-900">{title}</p>
          <span className="rounded-full bg-surface-muted px-2 py-0.5 text-xs font-semibold tabular-nums text-gray-600">
            {visible.length}
            {visible.length !== stores.length ? ` / ${stores.length}` : ""}
          </span>
        </div>
        {filters}
        <SearchBox value={query} onChange={setQuery} placeholder="Search name, code or city" />
      </div>
      <ul className="max-h-72 min-h-0 divide-y divide-surface-border overflow-y-auto lg:max-h-none lg:flex-1">
        {visible.length === 0 && <li className="px-4 py-10 text-center text-sm text-gray-500">No stores match.</li>}
        {visible.map((s) => {
          const active = s.id === selectedId;
          return (
            <li key={s.id}>
              <button
                type="button"
                onClick={() => onSelect(s.id)}
                aria-current={active}
                className={`flex w-full items-center gap-3 px-3.5 py-2.5 text-left transition-colors ${
                  active ? "bg-brand-50 shadow-[inset_3px_0_0_0_#2f6fed]" : "hover:bg-surface-subtle"
                }`}
              >
                <span className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-lg ${active ? "bg-brand-500 text-white" : "bg-surface-muted text-gray-500"}`}>
                  <IconStore className="h-4 w-4" />
                </span>
                <span className="min-w-0 flex-1">
                  <span className={`block truncate text-sm font-medium ${active ? "text-brand-700" : "text-gray-900"}`}>{s.name}</span>
                  <span className="block truncate text-xs text-gray-500">
                    {s.externalCode}
                    {s.city ? ` · ${s.city}` : ""}
                    {s.partnerName ? ` · ${s.partnerName}` : ""}
                  </span>
                </span>
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

export function SelectStorePrompt({ text = "Pick a store from the list to see its calendar." }: { text?: string }) {
  return (
    <div className="flex min-h-[18rem] flex-col items-center justify-center gap-2 rounded-xl border border-dashed border-surface-border bg-white px-6 py-12 text-center">
      <span className="flex h-12 w-12 items-center justify-center rounded-full bg-brand-50 text-brand-500">
        <IconStore className="h-6 w-6" />
      </span>
      <p className="text-sm font-semibold text-gray-800">No store selected</p>
      <p className="max-w-xs text-sm text-gray-500">{text}</p>
    </div>
  );
}

/** Region dropdown. Pass only the regions of the selected platform; the parent clears the value when the platform changes. */
export function RegionFilter({
  value,
  onChange,
  options,
  className = "",
}: {
  value: string;
  onChange: (v: string) => void;
  options: Option[];
  className?: string;
}) {
  return (
    <div className={`w-full sm:w-52 ${className}`}>
      <Select
        label="Region"
        value={options.some((o) => o.value === value) ? value : ""}
        onChange={(e) => onChange(e.target.value)}
        placeholder={`All regions (${options.length})`}
        options={options}
      />
    </div>
  );
}
