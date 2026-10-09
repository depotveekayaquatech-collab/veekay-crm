import { useEffect, useId, useMemo, useRef, useState, type ComponentType, type KeyboardEvent, type ReactNode, type SVGProps } from "react";
import { AnimatedNumber } from "@/components/ui/AnimatedNumber";
import { IconClose, IconSearch, IconStore } from "@/components/ui/icons";
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
    <div role="tablist" aria-label={label} className="inline-flex max-w-full gap-1 overflow-x-auto rounded-xl border border-surface-border bg-surface-muted/70 p-1">
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          role="tab"
          aria-selected={value === o.value}
          onClick={() => onChange(o.value)}
          className={`whitespace-nowrap rounded-lg px-3.5 py-[5px] text-sm font-semibold transition-[color,background-color,box-shadow] ${
            value === o.value
              ? "bg-surface text-brand-700 shadow-sm ring-1 ring-surface-border"
              : "text-gray-500 hover:text-gray-800"
          }`}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

/** Pill-shaped toggle with an optional count — for quick filters like "To mark (12)". */
export function FilterChip({ active, onClick, children, count }: { active: boolean; onClick: () => void; children: ReactNode; count?: number }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-sm font-semibold transition-colors ${
        active
          ? "border-brand-500/40 bg-brand-50 text-brand-700"
          : "border-surface-border bg-surface text-gray-600 hover:border-gray-300 hover:text-gray-900"
      }`}
    >
      {children}
      {count !== undefined && (
        <span className={`rounded-full px-1.5 text-xs tabular-nums ${active ? "bg-brand-500/20" : "bg-surface-muted text-gray-500"}`}>{count}</span>
      )}
    </button>
  );
}

/** Search field with a clear button. `hotkey` focuses it when "/" is pressed outside a field. */
export function SearchBox({
  value,
  onChange,
  placeholder,
  className = "",
  hotkey = false,
}: {
  value: string;
  onChange: (v: string) => void;
  placeholder: string;
  className?: string;
  hotkey?: boolean;
}) {
  const ref = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!hotkey) return;
    const onKey = (e: globalThis.KeyboardEvent) => {
      const t = e.target as HTMLElement | null;
      if (e.key !== "/" || e.ctrlKey || e.metaKey || e.altKey) return;
      if (t && (/^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName) || t.isContentEditable)) return;
      e.preventDefault();
      ref.current?.focus();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [hotkey]);

  return (
    <div className={`relative ${className}`}>
      <IconSearch aria-hidden="true" className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" />
      <input
        ref={ref}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={(e) => e.key === "Escape" && value && onChange("")}
        placeholder={placeholder}
        aria-label={placeholder}
        autoComplete="off"
        spellCheck={false}
        className="h-10 w-full rounded-lg border border-surface-border bg-surface pl-9 pr-9 text-sm shadow-sm outline-none transition-colors placeholder:text-gray-400 focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20"
      />
      {value ? (
        <button type="button" onClick={() => onChange("")} aria-label="Clear search" className="absolute right-2 top-1/2 -translate-y-1/2 rounded-md p-1 text-gray-400 hover:bg-surface-muted hover:text-gray-700">
          <IconClose className="h-4 w-4" aria-hidden="true" />
        </button>
      ) : (
        hotkey && <kbd className="pointer-events-none absolute right-2.5 top-1/2 hidden -translate-y-1/2 rounded border border-surface-border px-1.5 text-[10px] font-semibold text-gray-400 sm:block">/</kbd>
      )}
    </div>
  );
}

export function ProgressBar({ percent, className = "" }: { percent: number; className?: string }) {
  const p = Math.max(0, Math.min(100, percent));
  const tone = p >= 85 ? "from-status-success to-aqua-400" : p >= 50 ? "from-brand-500 to-aqua-400" : "from-status-warning to-status-warning/70";
  return (
    <div className={`h-2 overflow-hidden rounded-full bg-surface-muted ${className}`} role="progressbar" aria-valuenow={Math.round(p)} aria-valuemin={0} aria-valuemax={100}>
      <div className={`h-full rounded-full bg-gradient-to-r transition-[width] duration-500 ${tone}`} style={{ width: `${p}%` }} />
    </div>
  );
}

/** Circular gauge — the headline number of a page. */
export function ProgressRing({ percent, size = 112, label, sublabel }: { percent: number; size?: number; label?: ReactNode; sublabel?: string }) {
  const id = useId();
  const p = Math.max(0, Math.min(100, percent));
  const stroke = 10;
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  return (
    <div className="relative shrink-0" style={{ width: size, height: size }} role="img" aria-label={`${Math.round(p)} percent complete`}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="-rotate-90">
        <defs>
          <linearGradient id={id} x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" style={{ stopColor: "rgb(var(--brand-400))" }} />
            <stop offset="100%" style={{ stopColor: "rgb(var(--aqua-400))" }} />
          </linearGradient>
        </defs>
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" strokeWidth={stroke} className="stroke-surface-muted" />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          strokeWidth={stroke}
          strokeLinecap="round"
          stroke={`url(#${id})`}
          strokeDasharray={c}
          strokeDashoffset={c * (1 - p / 100)}
          className="transition-[stroke-dashoffset] duration-700 ease-out"
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="text-2xl font-extrabold tabular-nums text-heading">{label ?? `${Math.round(p)}%`}</span>
        {sublabel && <span className="text-[10px] font-semibold uppercase tracking-wider text-gray-500">{sublabel}</span>}
      </div>
    </div>
  );
}

const FILL = { brand: "stat-brand", aqua: "stat-aqua", success: "stat-success", warning: "stat-warning" } as const;

/** Filled gradient KPI card. Numbers count up; strings render as-is. */
export function StatCard({
  label,
  value,
  hint,
  tone = "brand",
  icon: Icon,
  children,
}: {
  label: string;
  value: ReactNode;
  hint?: ReactNode;
  tone?: keyof typeof FILL;
  /** Ignored — cards are filled gradients now. Kept so older call sites still compile. */
  valueClassName?: string;
  icon?: ComponentType<SVGProps<SVGSVGElement>>;
  children?: ReactNode;
}) {
  return (
    <div className={`${FILL[tone]} relative overflow-hidden rounded-2xl p-4 text-white shadow-md sm:p-5`}>
      <span aria-hidden="true" className="pointer-events-none absolute -right-8 -top-10 h-28 w-28 rounded-full bg-white/10" />
      <div className="relative flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-[11px] font-bold uppercase tracking-wider text-white/80">{label}</p>
          <p className="mt-1.5 text-[1.9rem] font-extrabold leading-none tabular-nums">
            {typeof value === "number" ? <AnimatedNumber value={value} /> : value}
          </p>
          {hint && <p className="mt-1.5 text-xs text-white/80">{hint}</p>}
        </div>
        {Icon && (
          <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-white/20">
            <Icon className="h-5 w-5" aria-hidden="true" />
          </span>
        )}
      </div>
      {children && <div className="relative [&_[role=progressbar]>div]:!bg-white [&_[role=progressbar]>div]:!bg-none [&_[role=progressbar]]:!bg-white/25">{children}</div>}
    </div>
  );
}

export function Avatar({ name, size = "md" }: { name: string; size?: "md" | "lg" }) {
  const parts = name.trim().split(/\s+/);
  const text = ((parts[0]?.[0] ?? "") + (parts[1]?.[0] ?? "")).toUpperCase() || "?";
  return (
    <span
      className={`flex shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-brand-400 to-aqua-400 font-bold text-white ${
        size === "lg" ? "h-11 w-11 text-sm" : "h-8 w-8 text-[11px]"
      }`}
    >
      {text}
    </span>
  );
}

/** Card with a titled header — the standard container for a block of content. */
export function Panel({ title, subtitle, action, children, flush }: { title: ReactNode; subtitle?: ReactNode; action?: ReactNode; children: ReactNode; flush?: boolean }) {
  return (
    <section className="overflow-hidden rounded-2xl border border-surface-border bg-surface shadow-card">
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-surface-border px-4 py-3.5 sm:px-5">
        <div className="min-w-0">
          <h3 className="text-sm font-bold text-heading">{title}</h3>
          {subtitle && <p className="mt-0.5 text-xs text-gray-500">{subtitle}</p>}
        </div>
        {action}
      </header>
      <div className={flush ? "" : "p-4 sm:p-5"}>{children}</div>
    </section>
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

/** Searchable store list — click (or ↑/↓ + Enter) to select a store. Used by "Mark orders" and "Correct entries". */
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
  const listRef = useRef<HTMLUListElement>(null);
  const visible = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return stores;
    return stores.filter((s) => [s.name, s.externalCode, s.city, s.state].some((f) => (f ?? "").toLowerCase().includes(q)));
  }, [stores, query]);

  function onKeyDown(e: KeyboardEvent<HTMLUListElement>) {
    if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
    const buttons = Array.from(listRef.current?.querySelectorAll("button") ?? []);
    const i = buttons.indexOf(document.activeElement as HTMLButtonElement);
    if (i === -1) return;
    e.preventDefault();
    buttons[Math.max(0, Math.min(buttons.length - 1, i + (e.key === "ArrowDown" ? 1 : -1)))]?.focus();
  }

  return (
    <div className="flex flex-col overflow-hidden rounded-2xl border border-surface-border bg-surface shadow-card lg:sticky lg:top-24 lg:max-h-[calc(100vh-7.5rem)]">
      <div className="flex shrink-0 flex-col gap-3 border-b border-surface-border p-3.5">
        <div className="flex items-center justify-between">
          <p className="text-sm font-bold text-heading">{title}</p>
          <span className="rounded-full bg-surface-muted px-2 py-0.5 text-xs font-semibold tabular-nums text-gray-600">
            {visible.length}
            {visible.length !== stores.length ? ` / ${stores.length}` : ""}
          </span>
        </div>
        {filters}
        <SearchBox value={query} onChange={setQuery} placeholder="Search name, code or city" />
      </div>
      <ul ref={listRef} onKeyDown={onKeyDown} className="max-h-72 min-h-0 divide-y divide-surface-border overflow-y-auto overscroll-contain lg:max-h-none lg:flex-1">
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
                  active ? "bg-brand-50 shadow-[inset_3px_0_0_0_rgb(var(--brand-500))]" : "hover:bg-surface-subtle"
                }`}
              >
                <span className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-lg ${active ? "bg-gradient-to-br from-brand-500 to-aqua-400 text-white" : "bg-surface-muted text-gray-500"}`}>
                  <IconStore className="h-4 w-4" aria-hidden="true" />
                </span>
                <span className="min-w-0 flex-1">
                  <span className={`block truncate text-sm font-semibold ${active ? "text-brand-700" : "text-gray-900"}`}>{s.name}</span>
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
    <div className="flex min-h-[18rem] flex-col items-center justify-center gap-2 rounded-2xl border border-dashed border-surface-border bg-surface px-6 py-12 text-center">
      <span className="flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-br from-brand-500/20 to-aqua-400/20 text-brand-600">
        <IconStore className="h-7 w-7" aria-hidden="true" />
      </span>
      <p className="text-sm font-bold text-gray-800">No store selected</p>
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
