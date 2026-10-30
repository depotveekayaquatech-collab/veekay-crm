import { useEffect, useId, useRef, useState } from "react";
import { Badge } from "@/components/ui/Badge";
import { useDebounced } from "@/hooks/useDebounced";
import { useEntrySummary, useFilterOptions, type PersonOption, type StoreOption } from "@/features/entries/api";
import { IconClose } from "@/components/ui/icons";

interface PickerProps {
  kind: "store" | "person";
  label: string;
  placeholder: string;
  /** The chosen id (empty = everyone / every store). */
  value: string;
  /** The name to show when the id was chosen somewhere else (a store clicked in the table). */
  valueLabel?: string;
  /** Employees only: list just the people of this partner. */
  platformId?: string;
  onPick: (id: string, label?: string) => void;
}

/**
 * A server-side typeahead for the Store-wise and Employee-wise filters: it asks the API for the 20 best matches inside the caller's own scope, so it stays
 * fast however many stores or people exist. The chosen name is remembered here; the parent only keeps the id.
 */
export function EntryPicker({ kind, label, placeholder, value, valueLabel, platformId = "", onPick }: PickerProps) {
  const id = useId();
  const [text, setText] = useState("");
  const [open, setOpen] = useState(false);
  const [chosen, setChosen] = useState<{ id: string; label: string } | null>(null);
  const q = useDebounced(text, 250);
  const options = useFilterOptions(kind, q, open && !value, platformId);
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const onDown = (e: MouseEvent) => { if (box.current && !box.current.contains(e.target as Node)) setOpen(false); };
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, []);

  const rows = open && options.data ? options.data : [];
  const labelOf = (o: StoreOption | PersonOption) => ("platform" in o ? `${o.name} (${o.code})` : `${o.name} (${o.code})${o.is_me ? " · you" : ""}`);

  return (
    <div className="flex flex-col gap-1.5" ref={box}>
      <label htmlFor={id} className="text-[12.5px] font-semibold text-gray-700">{label}</label>
      <div className="relative">
        {value ? (
          <div className="flex h-10 items-center justify-between gap-2 rounded-lg border border-brand-500/40 bg-brand-500/5 px-3 text-sm text-gray-900">
            <span className="truncate font-medium">{(chosen && chosen.id === value ? chosen.label : valueLabel) || "Selected"}</span>
            <button type="button" onClick={() => { onPick(""); setText(""); }} aria-label={`Clear ${label}`} className="rounded p-1 text-gray-500 hover:bg-surface-muted hover:text-gray-800">
              <IconClose className="h-4 w-4" aria-hidden="true" />
            </button>
          </div>
        ) : (
          <input
            id={id} value={text} placeholder={placeholder} autoComplete="off" role="combobox" aria-expanded={open} aria-controls={`${id}-list`}
            onChange={(e) => { setText(e.target.value); setOpen(true); }} onFocus={() => setOpen(true)}
            onKeyDown={(e) => { if (e.key === "Escape") setOpen(false); }}
            className="h-10 w-full rounded-lg border border-surface-border bg-surface px-3.5 text-sm text-gray-900 shadow-xs outline-none transition-[color,background-color,border-color,box-shadow,opacity,transform] placeholder:text-gray-400 focus:border-brand-500 focus:ring-3 focus:ring-brand-500/15"
          />
        )}
        {open && !value && (
          <ul id={`${id}-list`} role="listbox" className="absolute z-30 mt-1 max-h-64 w-full overflow-auto rounded-xl border border-surface-border bg-surface py-1 shadow-lg">
            {options.isLoading && <li className="px-3 py-2 text-sm text-gray-500">Searching…</li>}
            {!options.isLoading && rows.length === 0 && <li className="px-3 py-2 text-sm text-gray-500">No match. Try a name or code.</li>}
            {rows.map((o) => (
              <li key={o.id} role="option" aria-selected={false}>
                <button type="button" className="flex w-full flex-col px-3 py-1.5 text-left text-sm hover:bg-surface-subtle"
                  onClick={() => { setChosen({ id: o.id, label: labelOf(o) }); onPick(o.id, labelOf(o)); setOpen(false); setText(""); }}>
                  <span className="font-medium text-gray-900">{o.name}</span>
                  <span className="text-xs text-gray-500">{"platform" in o ? `${o.code}${o.crm_code ? ` · ${o.crm_code}` : ""} · ${o.platform}${o.status !== "LIVE" ? ` · ${o.status}` : ""}` : o.code}</span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

const CHIPS = [
  { value: "pending_l2", label: "Pending Team Lead", key: "pending_l2", tone: "warning" },
  { value: "requested", label: "Verification requested", key: "requested", tone: "warning" },
  { value: "verified_l2", label: "Verified by Team Lead", key: "verified_l2", tone: "info" },
  { value: "reviewed_l3", label: "Reviewed", key: "reviewed_l3", tone: "success" },
] as const;

/** Live counts per state over the last 30 days; each chip is also a shortcut to that status filter. */
export function StatusChips({ active, onPick }: { active: string; onPick: (status: string) => void }) {
  const { data } = useEntrySummary();
  return (
    <div className="flex flex-wrap items-center gap-2" aria-label="Entries by status, last 30 days">
      {CHIPS.map((c) => (
        <button key={c.value} type="button" onClick={() => onPick(active === c.value ? "" : c.value)} aria-pressed={active === c.value}
          className={`flex items-center gap-2 rounded-full border px-3 py-1.5 text-xs font-semibold transition-colors ${active === c.value ? "border-brand-500 bg-brand-500/10 text-brand-700" : "border-surface-border bg-surface text-gray-700 hover:bg-surface-subtle"}`}>
          {c.label}
          <Badge tone={c.tone}>{data ? data[c.key].toLocaleString() : "…"}</Badge>
        </button>
      ))}
      <span className="text-[11px] text-gray-400">last 30 days</span>
    </div>
  );
}
