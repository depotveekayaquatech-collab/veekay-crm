import { useEffect, useRef, useState, type ReactNode } from "react";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Skeleton } from "@/components/feedback/Skeleton";
import { useStores } from "@/features/vendor/useVendorData";
import { titleCase } from "@/features/vendor/format";
import type { Outcome, TicketStatus } from "@/features/vendor/vendorApi";

const STATUS_TONE: Record<TicketStatus, "info" | "warning" | "success" | "neutral"> = {
  OPEN: "warning", IN_PROGRESS: "info", RESOLVED: "success", CLOSED: "neutral",
};

export function TicketStatusBadge({ status }: { status: TicketStatus }) {
  return <Badge tone={STATUS_TONE[status]}>{titleCase(status)}</Badge>;
}

export function OutcomeBadge({ outcome }: { outcome: Outcome }) {
  const tone = outcome === "RECEIVED" ? "success" : outcome === "SHORT" ? "warning" : "danger";
  return <Badge tone={tone}>{titleCase(outcome)}</Badge>;
}

export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <div className={`rounded-xl border border-surface-border bg-surface p-4 shadow-sm ${className}`}>{children}</div>;
}

export function SectionTitle({ children, action }: { children: ReactNode; action?: ReactNode }) {
  return (
    <div className="mb-2 mt-5 flex items-center justify-between first:mt-0">
      <h2 className="text-sm font-bold text-heading">{children}</h2>
      {action}
    </div>
  );
}

export function ListSkeleton({ rows = 4 }: { rows?: number }) {
  return (
    <div className="flex flex-col gap-2" aria-busy="true" aria-label="Loading">
      {Array.from({ length: rows }, (_, i) => <Skeleton key={i} className="h-16 w-full" />)}
    </div>
  );
}

export function ErrorNote({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div role="alert" className="flex items-center justify-between gap-3 rounded-lg border border-status-danger/25 bg-status-danger-soft px-3 py-2.5 text-sm text-status-danger">
      <span>{message}</span>
      {onRetry && <Button size="sm" variant="secondary" onClick={onRetry}>Retry</Button>}
    </div>
  );
}

export function PageNav({ page, pageSize, total, onPage }: { page: number; pageSize: number; total: number; onPage: (p: number) => void }) {
  const pages = Math.max(1, Math.ceil(total / pageSize));
  if (pages <= 1) return null;
  return (
    <div className="mt-3 flex items-center justify-between text-sm text-gray-600">
      <Button size="sm" variant="secondary" disabled={page <= 1} onClick={() => onPage(page - 1)}>Previous</Button>
      <span>Page {page} of {pages}</span>
      <Button size="sm" variant="secondary" disabled={page >= pages} onClick={() => onPage(page + 1)}>Next</Button>
    </div>
  );
}

/** Store chooser for filters and forms: a button that opens a searchable full-screen list (vendors can have 50+ stores).
 * With a single store it is picked for you. */
export function StoreSelect({ value, onChange, allLabel, label = "Store" }: { value: string; onChange: (v: string) => void; allLabel?: string; label?: string }) {
  const { data: stores } = useStores();
  const [open, setOpen] = useState(false);
  const [needle, setNeedle] = useState("");
  const only = stores && stores.length === 1 ? stores[0].id : null;
  useEffect(() => {
    if (only && value !== only) onChange(only);
  }, [only, value, onChange]);

  const current = stores?.find((s) => s.id === value);
  const n = needle.trim().toLowerCase();
  const shown = (stores ?? []).filter((s) => !n || `${s.name} ${s.code} ${s.city ?? ""}`.toLowerCase().includes(n));

  function close() {
    setOpen(false);
    setNeedle("");
  }
  function pick(v: string) {
    onChange(v);
    close();
  }

  return (
    <div className="flex flex-col gap-1.5">
      <span className="text-[13px] font-semibold text-gray-700">{label}</span>
      <button
        type="button"
        disabled={Boolean(only)}
        onClick={() => setOpen(true)}
        className="flex h-12 w-full items-center justify-between gap-2 rounded-xl border border-surface-border bg-surface px-3.5 text-left text-sm shadow-sm disabled:bg-surface-subtle"
      >
        <span className={`min-w-0 truncate ${current || !value ? "text-gray-900" : "text-gray-400"}`}>
          {current ? current.name : allLabel ?? "Choose a store…"}
        </span>
        {!only && <span aria-hidden className="shrink-0 text-xs text-gray-400">{stores ? `${stores.length} stores` : ""} ▾</span>}
      </button>

      {open && (
        <div role="dialog" aria-modal="true" aria-label="Choose a store" className="fixed inset-0 z-50 flex flex-col bg-surface" onKeyDown={(e) => e.key === "Escape" && close()}>
          <div className="flex items-center gap-2 border-b border-surface-border px-3 pb-3 pt-[max(0.75rem,env(safe-area-inset-top))]">
            <input
              autoFocus
              type="search"
              value={needle}
              onChange={(e) => setNeedle(e.target.value)}
              placeholder="Search by name, code or city"
              aria-label="Search stores"
              className="h-11 min-w-0 flex-1 rounded-xl border border-surface-border bg-surface-subtle px-3.5 text-sm outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20"
            />
            <button type="button" onClick={close} className="h-11 shrink-0 px-2 text-sm font-semibold text-brand-600">Cancel</button>
          </div>
          <div className="flex-1 overflow-y-auto pb-[env(safe-area-inset-bottom)]">
            {allLabel !== undefined && !n && (
              <button type="button" onClick={() => pick("")} className={`flex w-full items-center justify-between border-b border-surface-border px-4 py-3.5 text-left text-sm font-semibold ${value === "" ? "text-brand-600" : "text-gray-900"}`}>
                {allLabel} {value === "" && <span aria-hidden>✓</span>}
              </button>
            )}
            {shown.map((s) => (
              <button key={s.id} type="button" onClick={() => pick(s.id)} className="flex w-full items-center justify-between gap-3 border-b border-surface-border px-4 py-3 text-left">
                <span className="min-w-0">
                  <span className={`block truncate text-sm font-semibold ${s.id === value ? "text-brand-600" : "text-gray-900"}`}>{s.name}</span>
                  <span className="block truncate text-xs text-gray-500">{s.code}{s.city ? ` · ${s.city}` : ""}{s.state ? `, ${s.state}` : ""}</span>
                </span>
                {s.id === value && <span aria-hidden className="text-brand-600">✓</span>}
              </button>
            ))}
            {shown.length === 0 && <p className="px-4 py-10 text-center text-sm text-gray-500">No store matches "{needle}".</p>}
          </div>
        </div>
      )}
    </div>
  );
}

function Thumb({ file }: { file: File }) {
  const [src, setSrc] = useState<string>();
  useEffect(() => {
    const reader = new FileReader();
    reader.onload = () => setSrc(String(reader.result));
    reader.readAsDataURL(file);
    return () => { reader.onload = null; };
  }, [file]);
  return src ? <img src={src} alt={file.name} className="h-full w-full object-cover" /> : <span className="block h-full w-full bg-surface-muted" />;
}

export function PhotoPicker({ files, onChange, max = 5, label = "Photos", accept = "image/*" }: { files: File[]; onChange: (f: File[]) => void; max?: number; label?: string; accept?: string }) {
  const input = useRef<HTMLInputElement>(null);
  return (
    <div className="flex flex-col gap-1.5">
      <span className="text-[13px] font-semibold text-gray-700">{label} <span className="font-normal text-gray-500">(up to {max})</span></span>
      <div className="flex flex-wrap gap-2">
        {files.map((f, i) => (
          <div key={`${f.name}-${i}`} className="relative h-20 w-20 overflow-hidden rounded-lg ring-1 ring-surface-border">
            {f.type.startsWith("image/") ? (
              <Thumb file={f} />
            ) : (
              <span className="flex h-full w-full items-center justify-center bg-surface-muted px-1 text-center text-[10px] font-semibold text-gray-600">{f.name.slice(-12)}</span>
            )}
            <button
              type="button"
              aria-label={`Remove ${f.name}`}
              onClick={() => onChange(files.filter((_, j) => j !== i))}
              className="absolute right-0.5 top-0.5 flex h-6 w-6 items-center justify-center rounded-full bg-black/60 text-xs text-white"
            >
              ×
            </button>
          </div>
        ))}
        {files.length < max && (
          <button
            type="button"
            onClick={() => input.current?.click()}
            className="flex h-20 w-20 flex-col items-center justify-center gap-0.5 rounded-lg border border-dashed border-gray-300 text-xs font-medium text-gray-600 hover:bg-surface-subtle"
          >
            <span className="text-lg leading-none">+</span>Add
          </button>
        )}
      </div>
      <input
        ref={input}
        type="file"
        accept={accept}
        multiple
        className="hidden"
        onChange={(e) => {
          onChange([...files, ...Array.from(e.target.files ?? [])].slice(0, max));
          e.target.value = "";
        }}
      />
    </div>
  );
}
