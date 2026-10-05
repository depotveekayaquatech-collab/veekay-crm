import { Badge } from "@/components/ui/Badge";
import type { DayStatus, LocationInfo } from "@/features/attendance/api";

const STATUS: Record<DayStatus, { label: string; tone: "success" | "info" | "warning" | "danger" | "neutral" }> = {
  CHECKED_IN: { label: "Checked in", tone: "success" },
  CHECKED_OUT: { label: "Checked out", tone: "info" },
  NO_CHECKOUT: { label: "No check-out", tone: "warning" },
  ON_LEAVE: { label: "On leave", tone: "info" },
  OFF: { label: "Weekly off", tone: "neutral" },
  ABSENT: { label: "Absent", tone: "danger" },
};

export function StatusBadge({ status }: { status: DayStatus }) {
  const s = STATUS[status];
  return <Badge tone={s.tone}>{s.label}</Badge>;
}

function km(m: number): string {
  return m >= 1000 ? `${(m / 1000).toFixed(1)} km` : `${m} m`;
}

/**
 * Where someone checked in: inside an office's radius it is just the office name; anywhere else the
 * exact coordinates are shown (with a map link, how accurate the reading was, and how far from the office).
 */
export function LocationBadge({ location }: { location: LocationInfo }) {
  if (location.status === "unknown") {
    return <span className="text-xs text-gray-400">{location.label === "—" ? "—" : "Location not shared"}</span>;
  }
  const detail = [
    location.accuracyM != null ? `±${location.accuracyM} m` : null,
    location.distanceM != null && location.status === "outside" ? `${km(location.distanceM)} from office` : null,
  ].filter(Boolean).join(" · ");

  if (location.status === "office") {
    return (
      <div title={[location.distanceM != null ? `${location.distanceM} m from the office centre` : null, detail].filter(Boolean).join(" · ")}>
        <Badge tone="success">{location.label}</Badge>
      </div>
    );
  }
  return (
    <div className="flex flex-col gap-0.5">
      <Badge tone="warning">Outside office</Badge>
      <a
        href={location.mapUrl}
        target="_blank"
        rel="noreferrer"
        className="font-mono text-[11px] font-medium text-brand-600 hover:text-brand-700"
        title="Open in Google Maps"
      >
        {location.label}
      </a>
      {detail && <span className="text-[11px] text-gray-500">{detail}</span>}
    </div>
  );
}

/** "All / Accounts / Blinkit employees / Zepto employees …" filter chips with counts. */
export function CategoryChips({
  rows,
  value,
  onChange,
}: {
  rows: { category: string; categoryLabel: string }[];
  value: string;
  onChange: (v: string) => void;
}) {
  const order = ["accounts", "blinkit", "zepto", "other"];
  const counts = new Map<string, { label: string; n: number }>();
  rows.forEach((r) => counts.set(r.category, { label: r.categoryLabel, n: (counts.get(r.category)?.n ?? 0) + 1 }));
  const present = order.filter((c) => counts.has(c));
  if (present.length < 2) return null; // nothing to choose between
  const chip = (id: string, label: string, n: number) => (
    <button
      key={id}
      onClick={() => onChange(id)}
      className={`rounded-lg px-3 py-1.5 text-sm font-semibold transition-colors ${
        value === id ? "bg-brand-500 text-white shadow-sm" : "bg-surface text-gray-600 ring-1 ring-surface-border hover:bg-surface-subtle"
      }`}
    >
      {label} <span className={value === id ? "text-white/70" : "text-gray-400"}>{n}</span>
    </button>
  );
  return (
    <div className="flex flex-wrap gap-1.5" role="tablist" aria-label="Category">
      {chip("", "All", rows.length)}
      {present.map((c) => chip(c, counts.get(c)!.label, counts.get(c)!.n))}
    </div>
  );
}

/** A full-width heading row that starts each category group in a table. */
export function GroupRow({ colSpan, label, count }: { colSpan: number; label: string; count: number }) {
  return (
    <tr>
      <td colSpan={colSpan} className="border-y border-surface-border bg-surface-muted/70 px-4 py-2 text-[11px] font-bold uppercase tracking-wider text-gray-600">
        {label} <span className="ml-1 font-semibold text-gray-400">· {count}</span>
      </td>
    </tr>
  );
}
