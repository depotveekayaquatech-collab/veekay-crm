import { useEffect, useId, useMemo, useRef, useState } from "react";
import { IconChevronDown } from "@/components/ui/icons";

interface Props {
  label: string;
  options: { value: string; label: string; hint?: string }[];
  value: string[];
  onChange: (next: string[]) => void;
  /** What the closed control says when nothing is chosen, e.g. "All regions". */
  allLabel: string;
  className?: string;
}

/** A labelled dropdown where several options can be ticked. Closes on a click outside or Escape; long lists get a search box. */
export function MultiSelect({ label, options, value, onChange, allLabel, className = "" }: Props) {
  const [open, setOpen] = useState(false);
  const [needle, setNeedle] = useState("");
  const root = useRef<HTMLDivElement>(null);
  const id = useId();

  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => { if (!root.current?.contains(e.target as Node)) setOpen(false); };
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onKey);
    return () => { document.removeEventListener("mousedown", onDoc); document.removeEventListener("keydown", onKey); };
  }, [open]);

  const shown = useMemo(() => {
    const n = needle.trim().toLowerCase();
    return n ? options.filter((o) => `${o.label} ${o.hint ?? ""}`.toLowerCase().includes(n)) : options;
  }, [options, needle]);
  const chosen = new Set(value);
  const summary = value.length === 0 ? allLabel : value.length === 1 ? (options.find((o) => o.value === value[0])?.label ?? "1 selected") : `${value.length} selected`;
  const toggle = (v: string) => onChange(chosen.has(v) ? value.filter((x) => x !== v) : [...value, v]);

  return (
    <div ref={root} className={`relative flex flex-col gap-1.5 ${className}`}>
      <label htmlFor={id} className="text-[12.5px] font-semibold text-gray-700">{label}</label>
      <button
        id={id} type="button" aria-haspopup="listbox" aria-expanded={open} onClick={() => setOpen((o) => !o)}
        className="flex h-10 w-full items-center justify-between gap-2 rounded-lg border border-surface-border bg-surface px-3 text-left text-sm shadow-sm outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20"
      >
        <span className={`truncate ${value.length ? "font-medium text-gray-900" : "text-gray-500"}`}>{summary}</span>
        <IconChevronDown className="h-4 w-4 shrink-0 text-gray-400" aria-hidden="true" />
      </button>
      {open && (
        <div className="absolute left-0 top-full z-40 mt-1 w-full min-w-[15rem] rounded-xl border border-surface-border bg-surface p-2 shadow-lg" role="listbox" aria-multiselectable="true">
          {options.length > 8 && (
            <input autoFocus value={needle} onChange={(e) => setNeedle(e.target.value)} placeholder="Search…" aria-label={`Search ${label}`}
              className="mb-2 h-9 w-full rounded-lg border border-surface-border bg-surface px-3 text-sm outline-none focus:border-brand-500" />
          )}
          <div className="mb-1 flex items-center justify-between px-1 text-[11px] font-semibold">
            <button type="button" className="text-brand-600 hover:underline" onClick={() => onChange(shown.map((o) => o.value))}>Select shown</button>
            <button type="button" className="text-gray-500 hover:underline" onClick={() => onChange([])}>Clear</button>
          </div>
          <ul className="max-h-60 overflow-auto">
            {shown.length === 0 && <li className="px-2 py-3 text-center text-xs text-gray-500">Nothing matches.</li>}
            {shown.map((o) => (
              <li key={o.value}>
                <label className="flex cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-sm hover:bg-surface-subtle">
                  <input type="checkbox" checked={chosen.has(o.value)} onChange={() => toggle(o.value)} className="h-4 w-4 rounded border-surface-border text-brand-500" />
                  <span className="min-w-0 flex-1 truncate">{o.label}</span>
                  {o.hint && <span className="text-xs text-gray-400">{o.hint}</span>}
                </label>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
