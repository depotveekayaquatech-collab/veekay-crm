import { useEffect, useId, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { IconSearch, IconStore } from "@/components/ui/icons";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { listStores } from "@/services/stores";
import { readRecent, rememberRecent } from "@/lib/recentPages";

export interface PaletteLink {
  label: string;
  to: string;
}

interface Result {
  key: string;
  label: string;
  hint?: string;
  to: string;
  kind: "Page" | "Store" | "Recent";
  /** A second, quieter destination for the same row (a store's orders calendar), shown only to people allowed to open it. */
  also?: { label: string; to: string };
}

/**
 * Ctrl/⌘+K quick switcher. Pages come from the navigation the person is already allowed to see; stores come from the server's own search, so they are limited to
 * the stores that person may see and are never all loaded into the browser. A store opens the Stores page narrowed to it; people who can open orders also get an
 * "Orders" shortcut straight to that store's calendar.
 */
export function CommandPalette({
  open,
  onClose,
  pages,
  canSearchStores,
  canOpenOrders = false,
  recentKey,
}: {
  open: boolean;
  onClose: () => void;
  pages: PaletteLink[];
  canSearchStores: boolean;
  canOpenOrders?: boolean;
  recentKey?: string;
}) {
  const navigate = useNavigate();
  const inputRef = useRef<HTMLInputElement>(null);
  const listId = useId();
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const [debounced, setDebounced] = useState("");

  useEffect(() => {
    const id = setTimeout(() => setDebounced(query.trim()), 250);
    return () => clearTimeout(id);
  }, [query]);

  // Server-side search, so every store is findable however many there are.
  const { data: storePage, isFetching, isError } = useQuery({
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
    const known = new Map(pages.map((p) => [p.to, p]));
    // With nothing typed: the pages this person opened last (still only pages they may see), then everything else.
    const recent = !q && recentKey ? readRecent(recentKey).filter((r) => known.has(r.to)) : [];
    const recentHits = recent.map<Result>((p) => ({ key: `r:${p.to}`, label: known.get(p.to)!.label, to: p.to, kind: "Recent" }));
    const pageHits = pages
      .filter((p) => (q ? p.label.toLowerCase().includes(q) : !recent.some((r) => r.to === p.to)))
      .map<Result>((p) => ({ key: `p:${p.to}`, label: p.label, to: p.to, kind: "Page" }));
    const storeHits = q && searching
      ? (storePage?.items ?? []).map<Result>((s) => ({
          key: `s:${s.id}`,
          label: s.name,
          hint: [s.externalCode, s.city, s.partnerName].filter(Boolean).join(", "),
          to: `/stores?search=${encodeURIComponent(s.externalCode || s.name)}`,
          kind: "Store",
          also: canOpenOrders ? { label: "Orders", to: `/orders?store=${s.id}` } : undefined,
        }))
      : [];
    return [...recentHits, ...pageHits, ...storeHits];
  }, [query, pages, storePage, searching, recentKey, canOpenOrders]);

  // Keep the highlighted row inside the visible part of the list while arrowing through it.
  useEffect(() => {
    if (open) document.getElementById(`${listId}-${active}`)?.scrollIntoView({ block: "nearest" });
  }, [active, open, listId]);

  if (!open) return null;

  function close() {
    setQuery("");
    setActive(0);
    onClose();
  }

  function go(to: string, page?: PaletteLink) {
    if (page && recentKey) rememberRecent(recentKey, page);
    navigate(to);
    close();
  }

  function choose(r: Result | undefined) {
    if (!r) return;
    go(r.to, r.kind === "Store" ? undefined : { label: r.label, to: r.to });
  }

  function onKeyDown(e: React.KeyboardEvent) {
    if (e.key === "Escape") close();
    else if (e.key === "ArrowDown") {
      e.preventDefault();
      setActive((i) => Math.min(i + 1, results.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((i) => Math.max(i - 1, 0));
    } else if (e.key === "Enter") {
      const r = results[active];
      if (e.shiftKey && r?.also) go(r.also.to);                       // Shift+Enter: the second destination
      else choose(r);
    }
  }

  const status = searching && canSearchStores
    ? isError ? "Stores could not be searched just now. Pages still work." : isFetching ? "Searching stores…" : ""
    : "";

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center px-4 pt-[14vh]" onKeyDown={onKeyDown}>
      <div className="absolute inset-0 animate-fade-in bg-ink-950/50" onClick={close} aria-hidden="true" />
      <div role="dialog" aria-modal="true" aria-label="Command palette" className="relative w-full max-w-xl animate-slide-up overflow-hidden rounded-xl border border-surface-border bg-surface shadow-lg">
        <div className="flex items-center gap-3 border-b border-surface-border px-4">
          <IconSearch className="h-5 w-5 text-gray-400" aria-hidden="true" />
          <input
            ref={inputRef}
            value={query}
            role="combobox"
            aria-expanded="true"
            aria-controls={listId}
            aria-activedescendant={results[active] ? `${listId}-${active}` : undefined}
            onChange={(e) => {
              setQuery(e.target.value);
              setActive(0);
            }}
            placeholder={canSearchStores ? "Jump to a page or search stores" : "Jump to a page"}
            aria-label="Search pages and stores"
            className="h-14 flex-1 bg-transparent text-base text-gray-900 outline-none placeholder:text-gray-400 focus-visible:shadow-none sm:text-sm"
          />
          <kbd className="rounded border border-surface-border px-1.5 py-0.5 text-[11px] font-medium text-gray-400">Esc</kbd>
        </div>
        <ul id={listId} role="listbox" className="max-h-80 overflow-y-auto p-2">
          {results.length === 0 && !status && <li className="px-3 py-8 text-center text-sm text-gray-500">{query.trim() ? "Nothing matches. Try a store name, code or city, or a page name." : "No pages available."}</li>}
          {results.map((r, i) => (
            <li key={r.key} role="option" id={`${listId}-${i}`} aria-selected={i === active}>
              <div
                onMouseEnter={() => setActive(i)}
                className={`flex w-full items-center gap-2 rounded-lg pr-2 text-sm ${i === active ? "bg-brand-50 text-brand-700" : "text-gray-700"}`}
              >
                <button type="button" tabIndex={-1} onClick={() => choose(r)} className="flex min-h-11 min-w-0 flex-1 items-center gap-3 rounded-lg px-3 py-2 text-left">
                  {r.kind === "Store" && <IconStore className="h-4 w-4 shrink-0 text-gray-400" aria-hidden="true" />}
                  <span className="min-w-0 flex-1">
                    <span className="block truncate font-medium">{r.label}</span>
                    {r.hint && <span className="block truncate text-xs text-gray-500">{r.hint}</span>}
                  </span>
                  <span className="text-xs font-medium text-gray-400">{r.kind}</span>
                </button>
                {r.also && (
                  <button type="button" tabIndex={-1} onClick={() => go(r.also!.to)} title="Shift+Enter" className="min-h-9 shrink-0 rounded-md border border-surface-border bg-surface px-2.5 text-xs font-semibold text-brand-700 hover:border-brand-400">
                    {r.also.label}
                  </button>
                )}
              </div>
            </li>
          ))}
          {status && <li className="px-3 py-3 text-center text-xs text-gray-500" role="status">{status}</li>}
        </ul>
        <div className="flex items-center gap-4 border-t border-surface-border bg-surface-subtle/60 px-4 py-2 text-xs text-gray-500">
          <span>Up and down to move</span>
          <span>Enter to open</span>
          {canOpenOrders && canSearchStores && <span>Shift+Enter for a store&apos;s orders</span>}
        </div>
      </div>
    </div>
  );
}
