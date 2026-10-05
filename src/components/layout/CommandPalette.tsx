import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { IconSearch, IconStore } from "@/components/ui/icons";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { listStores } from "@/services/stores";

export interface PaletteLink {
  label: string;
  to: string;
}

interface Result {
  key: string;
  label: string;
  hint?: string;
  to: string;
  kind: "Page" | "Store";
}

/** Ctrl/⌘+K quick switcher: jump to any page or find a store by name/code/city. */
export function CommandPalette({
  open,
  onClose,
  pages,
  canSearchStores,
}: {
  open: boolean;
  onClose: () => void;
  pages: PaletteLink[];
  canSearchStores: boolean;
}) {
  const navigate = useNavigate();
  const inputRef = useRef<HTMLInputElement>(null);
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const [debounced, setDebounced] = useState("");

  useEffect(() => {
    const id = setTimeout(() => setDebounced(query.trim()), 250);
    return () => clearTimeout(id);
  }, [query]);

  // Server-side search, so every store is findable however many there are.
  const { data: storePage } = useQuery({
    queryKey: ["stores", "search", debounced],
    queryFn: () => listStores({ page: 1, pageSize: 8, search: debounced }),
    enabled: open && canSearchStores && debounced.length >= 2,
    placeholderData: keepPreviousData,
  });
  const searching = debounced.length >= 2;

  useEffect(() => {
    if (open) inputRef.current?.focus();
  }, [open]);

  const results = useMemo<Result[]>(() => {
    const q = query.trim().toLowerCase();
    const pageHits = pages
      .filter((p) => !q || p.label.toLowerCase().includes(q))
      .map<Result>((p) => ({ key: `p:${p.to}`, label: p.label, to: p.to, kind: "Page" }));
    const storeHits = q && searching
      ? (storePage?.items ?? [])
          .map<Result>((s) => ({
            key: `s:${s.id}`,
            label: s.name,
            hint: [s.externalCode, s.city, s.partnerName].filter(Boolean).join(" · "),
            to: "/stores",
            kind: "Store",
          }))
      : [];
    return [...pageHits, ...storeHits];
  }, [query, pages, storePage, searching]);

  if (!open) return null;

  function close() {
    setQuery("");
    setActive(0);
    onClose();
  }

  function choose(r: Result | undefined) {
    if (!r) return;
    navigate(r.to);
    close();
  }

  function onKeyDown(e: React.KeyboardEvent) {
    if (e.key === "Escape") close();
    else if (e.key === "ArrowDown") {
      e.preventDefault();
      setActive((i) => Math.min(i + 1, results.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((i) => Math.max(i - 1, 0));
    } else if (e.key === "Enter") choose(results[active]);
  }

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center px-4 pt-[14vh]" onKeyDown={onKeyDown}>
      <div className="absolute inset-0 animate-fade-in bg-ink-950/50 backdrop-blur-sm" onClick={close} aria-hidden="true" />
      <div
        role="dialog"
        aria-label="Command palette"
        className="relative w-full max-w-xl animate-slide-up overflow-hidden rounded-2xl border border-surface-border bg-surface shadow-lg"
      >
        <div className="flex items-center gap-3 border-b border-surface-border px-4">
          <IconSearch className="h-5 w-5 text-gray-400" />
          <input
            ref={inputRef}
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setActive(0);
            }}
            placeholder="Jump to a page or search stores…"
            className="h-14 flex-1 bg-transparent text-sm text-gray-900 outline-none placeholder:text-gray-400"
          />
          <kbd className="rounded border border-surface-border px-1.5 py-0.5 text-[10px] font-semibold text-gray-400">ESC</kbd>
        </div>
        <ul className="max-h-80 overflow-y-auto p-2">
          {results.length === 0 && <li className="px-3 py-8 text-center text-sm text-gray-500">No results.</li>}
          {results.map((r, i) => (
            <li key={r.key}>
              <button
                onMouseEnter={() => setActive(i)}
                onClick={() => choose(r)}
                className={`flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left text-sm ${
                  i === active ? "bg-brand-50 text-brand-700" : "text-gray-700"
                }`}
              >
                {r.kind === "Store" && <IconStore className="h-4 w-4 shrink-0 text-gray-400" />}
                <span className="min-w-0 flex-1">
                  <span className="block truncate font-medium">{r.label}</span>
                  {r.hint && <span className="block truncate text-xs text-gray-500">{r.hint}</span>}
                </span>
                <span className="text-[10px] font-semibold uppercase tracking-wider text-gray-400">{r.kind}</span>
              </button>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
