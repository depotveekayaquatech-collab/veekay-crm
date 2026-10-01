import {
  Children,
  isValidElement,
  useEffect,
  useId,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type ChangeEvent,
  type KeyboardEvent,
  type ReactElement,
  type ReactNode,
} from "react";
import { createPortal } from "react-dom";
import { IconCheckCircle, IconChevronDown, IconSearch } from "@/components/ui/icons";

export interface DropdownOption {
  value: string;
  label: string;
  disabled?: boolean;
}

interface DropdownProps {
  value: string;
  onValueChange: (value: string) => void;
  options: DropdownOption[];
  /** Label of the empty choice. When set, an entry with value "" is offered first. */
  placeholder?: string;
  disabled?: boolean;
  invalid?: boolean;
  id?: string;
  "aria-label"?: string;
  /** Wrapper classes — width only; the control itself is always styled the same way. */
  className?: string;
  /** Show a search box. Defaults to on for long lists. */
  searchable?: boolean;
}

const SEARCH_THRESHOLD = 8;
const PANEL_MAX = 320;

/**
 * The one dropdown used across the app: a styled trigger plus a floating list (rendered in a portal, so it is
 * never clipped by cards or modals), keyboard-navigable, with a search box for long lists.
 */
export function Dropdown({
  value,
  onValueChange,
  options,
  placeholder,
  disabled,
  invalid,
  id,
  "aria-label": ariaLabel,
  className = "",
  searchable,
}: DropdownProps) {
  const autoId = useId();
  const listId = `${id ?? autoId}-list`;
  const trigger = useRef<HTMLButtonElement>(null);
  const panel = useRef<HTMLDivElement>(null);
  const searchBox = useRef<HTMLInputElement>(null);
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const [pos, setPos] = useState<{ left: number; width: number; top?: number; bottom?: number; maxHeight: number } | null>(null);

  const all = useMemo<DropdownOption[]>(
    () => (placeholder !== undefined ? [{ value: "", label: placeholder }, ...options] : options),
    [options, placeholder],
  );
  const showSearch = searchable ?? options.length > SEARCH_THRESHOLD;
  const visible = useMemo(() => {
    const q = query.trim().toLowerCase();
    return q ? all.filter((o) => o.label.toLowerCase().includes(q)) : all;
  }, [all, query]);

  const current = all.find((o) => o.value === value);
  const isPlaceholder = !current || (current.value === "" && placeholder !== undefined);

  function close() {
    setOpen(false);
    setQuery("");
  }

  function openPanel() {
    if (disabled) return;
    setActive(Math.max(0, all.findIndex((o) => o.value === value)));
    setOpen(true);
  }

  function choose(o: DropdownOption) {
    if (o.disabled) return;
    onValueChange(o.value);
    close();
    trigger.current?.focus();
  }

  // Position under the trigger (flip above when there's no room); keep it glued while the page moves.
  useLayoutEffect(() => {
    if (!open) return;
    function place() {
      const r = trigger.current?.getBoundingClientRect();
      if (!r) return;
      const below = window.innerHeight - r.bottom - 12;
      const above = r.top - 12;
      const flip = below < 200 && above > below;
      const room = Math.min(PANEL_MAX, flip ? above : below);
      const width = Math.max(r.width, 176);
      const left = Math.min(Math.max(8, r.left), window.innerWidth - width - 8);
      setPos(
        flip
          ? { left, width, bottom: window.innerHeight - r.top + 6, maxHeight: room }
          : { left, width, top: r.bottom + 6, maxHeight: room },
      );
    }
    place();
    window.addEventListener("resize", place);
    window.addEventListener("scroll", place, true);
    return () => {
      window.removeEventListener("resize", place);
      window.removeEventListener("scroll", place, true);
    };
  }, [open]);

  useEffect(() => {
    if (!open) return;
    function onDown(e: MouseEvent) {
      const t = e.target as Node;
      if (!panel.current?.contains(t) && !trigger.current?.contains(t)) close();
    }
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [open]);

  useEffect(() => {
    if (open && showSearch) searchBox.current?.focus();
  }, [open, showSearch]);

  // Keep the highlighted row in view.
  useEffect(() => {
    if (open) panel.current?.querySelector<HTMLElement>(`[data-index="${active}"]`)?.scrollIntoView({ block: "nearest" });
  }, [active, open]);

  function onKey(e: KeyboardEvent) {
    if (!open) {
      if (["ArrowDown", "ArrowUp", "Enter", " "].includes(e.key)) {
        e.preventDefault();
        openPanel();
      }
      return;
    }
    if (e.key === "Escape") {
      e.preventDefault();
      close();
      trigger.current?.focus();
    } else if (e.key === "ArrowDown") {
      e.preventDefault();
      setActive((i) => Math.min(visible.length - 1, i + 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((i) => Math.max(0, i - 1));
    } else if (e.key === "Enter") {
      e.preventDefault();
      if (visible[active]) choose(visible[active]);
    } else if (e.key === "Tab") {
      close();
    }
  }

  return (
    <div className={`relative ${className}`} onKeyDown={onKey}>
      <button
        ref={trigger}
        id={id}
        type="button"
        role="combobox"
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={listId}
        aria-label={ariaLabel}
        aria-invalid={invalid || undefined}
        disabled={disabled}
        onClick={() => (open ? close() : openPanel())}
        className={`group flex h-10 w-full font-medium normal-case tracking-normal items-center justify-between gap-2 rounded-lg border bg-white pl-3 pr-2.5 text-left text-sm shadow-sm outline-none transition-all disabled:cursor-not-allowed disabled:bg-surface-subtle disabled:text-gray-400 ${
          invalid
            ? "border-status-danger"
            : open
              ? "border-brand-500 ring-2 ring-brand-500/20"
              : "border-surface-border hover:border-gray-300 focus-visible:border-brand-500 focus-visible:ring-2 focus-visible:ring-brand-500/20"
        }`}
      >
        <span className={`truncate ${isPlaceholder ? "text-gray-500" : "font-medium text-gray-900"}`}>{current?.label ?? placeholder ?? "Select…"}</span>
        <IconChevronDown className={`h-4 w-4 shrink-0 text-gray-400 transition-transform group-hover:text-gray-600 ${open ? "rotate-180 text-brand-500" : ""}`} />
      </button>

      {open &&
        pos &&
        createPortal(
          <div
            ref={panel}
            style={{ position: "fixed", left: pos.left, width: pos.width, top: pos.top, bottom: pos.bottom, maxHeight: pos.maxHeight }}
            className="z-[200] flex animate-fade-in flex-col overflow-hidden rounded-xl border border-surface-border bg-white shadow-lg ring-1 ring-black/5"
          >
            {showSearch && (
              <div className="relative shrink-0 border-b border-surface-border p-2">
                <IconSearch className="pointer-events-none absolute left-4 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" />
                <input
                  ref={searchBox}
                  value={query}
                  onChange={(e) => {
                    setQuery(e.target.value);
                    setActive(0);
                  }}
                  placeholder="Search…"
                  aria-label="Search options"
                  className="h-9 w-full rounded-md bg-surface-subtle pl-8 pr-2 text-sm outline-none placeholder:text-gray-400 focus:bg-white focus:ring-2 focus:ring-brand-500/20"
                />
              </div>
            )}
            <ul id={listId} role="listbox" className="min-h-0 flex-1 overflow-y-auto p-1.5">
              {visible.length === 0 && <li className="px-3 py-6 text-center text-sm text-gray-500">No matches</li>}
              {visible.map((o, i) => {
                const selected = o.value === value;
                return (
                  <li
                    key={o.value || "__empty"}
                    role="option"
                    aria-selected={selected}
                    aria-disabled={o.disabled}
                    data-index={i}
                    onMouseEnter={() => setActive(i)}
                    onClick={() => choose(o)}
                    className={`flex cursor-pointer items-center justify-between gap-2 rounded-lg px-3 py-2 text-sm transition-colors ${
                      o.disabled
                        ? "cursor-not-allowed text-gray-300"
                        : i === active
                          ? "bg-brand-50 text-brand-700"
                          : "text-gray-700"
                    } ${selected ? "font-semibold" : ""}`}
                  >
                    <span className="truncate">{o.label}</span>
                    {selected && <IconCheckCircle className="h-4 w-4 shrink-0 text-brand-500" />}
                  </li>
                );
              })}
            </ul>
          </div>,
          document.body,
        )}
    </div>
  );
}

/* ---- drop-in for a native <select> with <option> children ---- */

function textOf(node: ReactNode): string {
  if (node == null || typeof node === "boolean") return "";
  if (typeof node === "string" || typeof node === "number") return String(node);
  if (Array.isArray(node)) return node.map(textOf).join("");
  if (isValidElement(node)) return textOf((node.props as { children?: ReactNode }).children);
  return "";
}

function collect(children: ReactNode, out: DropdownOption[]) {
  Children.forEach(children, (child) => {
    if (!isValidElement(child)) return;
    const el = child as ReactElement<{ value?: string | number; disabled?: boolean; children?: ReactNode }>;
    if (el.type === "option") {
      const label = textOf(el.props.children);
      out.push({ value: el.props.value !== undefined ? String(el.props.value) : label, label, disabled: el.props.disabled });
    } else if (el.props.children) {
      collect(el.props.children, out); // fragments, <optgroup>
    }
  });
}

// Only layout-ish classes carry over from the old native-select styling; the look comes from <Dropdown>.
const KEEP = /^(?:(?:sm|md|lg|xl):)?(?:w-|min-w-|max-w-|flex-|grow|shrink|basis-|col-span-)/;

interface SelectFieldProps {
  value: string | number;
  onChange: (e: ChangeEvent<HTMLSelectElement>) => void;
  children: ReactNode;
  className?: string;
  disabled?: boolean;
  id?: string;
  "aria-label"?: string;
}

/**
 * Same props as `<select>` (value, onChange(e) → e.target.value, <option> children) rendered as a <Dropdown>.
 * The option with an empty value, if any, becomes the "no selection" entry.
 */
export function SelectField({ value, onChange, children, className = "", ...rest }: SelectFieldProps) {
  const opts: DropdownOption[] = [];
  collect(children, opts);
  const empty = opts.find((o) => o.value === "");
  const rest2 = opts.filter((o) => o.value !== "");
  const wrapper = className.split(/\s+/).filter((c) => KEEP.test(c)).join(" ");

  return (
    <Dropdown
      {...rest}
      className={wrapper || "w-full"}
      value={String(value)}
      options={rest2}
      placeholder={empty?.label}
      onValueChange={(v) => onChange({ target: { value: v }, currentTarget: { value: v } } as unknown as ChangeEvent<HTMLSelectElement>)}
    />
  );
}
