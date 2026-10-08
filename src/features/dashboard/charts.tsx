/**
 * Dependency-free SVG charts. Kept tiny and presentational — all data
 * shaping happens in the caller. Matches the icon set's "one visual
 * language, no libraries" approach.
 */
import { useId, useState, type KeyboardEvent, type PointerEvent } from "react";

/* ------------------------------------------------------------------ */
/* Area / line chart                                                   */
/* ------------------------------------------------------------------ */

export interface AreaPoint {
  label: string;
  value: number;
}

export function AreaChart({
  data,
  height = 180,
  valueSuffix = "",
  selected = null,
  onSelect,
}: {
  data: AreaPoint[];
  height?: number;
  valueSuffix?: string;
  /** Index of the pinned point (e.g. the day being inspected). */
  selected?: number | null;
  /** Called when a point is clicked or picked with the arrow keys; enables the interactive mode. */
  onSelect?: (index: number) => void;
}) {
  const [hover, setHover] = useState<number | null>(null);
  const uid = useId();
  const gradientId = `${uid}-fill`;
  const strokeId = `${uid}-stroke`;
  const w = 640;
  const h = height;
  const padX = 8;
  const padY = 16;
  const max = Math.max(1, ...data.map((d) => d.value));
  const stepX = data.length > 1 ? (w - padX * 2) / (data.length - 1) : 0;

  const pts = data.map((d, i) => {
    const x = padX + i * stepX;
    const y = padY + (1 - d.value / max) * (h - padY * 2);
    return [x, y] as const;
  });

  const line = pts.map(([x, y], i) => `${i === 0 ? "M" : "L"}${x.toFixed(1)} ${y.toFixed(1)}`).join(" ");
  const area = `${line} L${pts[pts.length - 1]?.[0].toFixed(1)} ${h - padY} L${pts[0]?.[0].toFixed(1)} ${h - padY} Z`;

  const active = hover ?? selected;
  const activePt = active !== null && active >= 0 && active < pts.length ? pts[active] : null;

  function indexAt(e: PointerEvent<HTMLDivElement>): number {
    const rect = e.currentTarget.getBoundingClientRect();
    const f = rect.width ? (e.clientX - rect.left) / rect.width : 0;
    return Math.max(0, Math.min(data.length - 1, Math.round(f * (data.length - 1))));
  }

  function onKeyDown(e: KeyboardEvent<HTMLDivElement>) {
    if (!onSelect || (e.key !== "ArrowLeft" && e.key !== "ArrowRight")) return;
    e.preventDefault();
    const cur = selected ?? data.length - 1;
    onSelect(Math.max(0, Math.min(data.length - 1, cur + (e.key === "ArrowRight" ? 1 : -1))));
  }

  return (
    <div className="w-full">
      <div
        className={`relative ${onSelect ? "cursor-crosshair touch-none rounded-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500" : ""}`}
        tabIndex={onSelect ? 0 : undefined}
        onKeyDown={onKeyDown}
        onPointerMove={onSelect ? (e) => setHover(indexAt(e)) : undefined}
        onPointerLeave={onSelect ? () => setHover(null) : undefined}
        onClick={onSelect ? (e) => onSelect(indexAt(e as unknown as PointerEvent<HTMLDivElement>)) : undefined}
        aria-label={onSelect ? "Trend chart. Use the arrow keys to move between days." : undefined}
      >
      <svg viewBox={`0 0 ${w} ${h}`} className="w-full" preserveAspectRatio="none" role="img" aria-label="Trend chart">
        <defs>
          <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" style={{ stopColor: "rgb(var(--brand-500))" }} stopOpacity="0.35" />
            <stop offset="100%" style={{ stopColor: "rgb(var(--aqua-400))" }} stopOpacity="0" />
          </linearGradient>
          <linearGradient id={strokeId} x1="0" y1="0" x2="1" y2="0">
            <stop offset="0%" style={{ stopColor: "rgb(var(--brand-400))" }} />
            <stop offset="100%" style={{ stopColor: "rgb(var(--aqua-400))" }} />
          </linearGradient>
        </defs>
        {[0.25, 0.5, 0.75].map((f) => (
          <line
            key={f}
            x1={padX}
            x2={w - padX}
            y1={padY + f * (h - padY * 2)}
            y2={padY + f * (h - padY * 2)}
            className="stroke-surface-border"
            strokeWidth={1}
            strokeDasharray="3 4"
          />
        ))}
        <path d={area} fill={`url(#${gradientId})`} />
        <path d={line} fill="none" stroke={`url(#${strokeId})`} strokeWidth={2.5} strokeLinejoin="round" strokeLinecap="round" />
        {pts.map(([x, y], i) => (
          <circle key={i} cx={x} cy={y} r={data.length > 20 || onSelect ? 0 : 3} className="fill-surface stroke-aqua-400" strokeWidth={2}>
            <title>{`${data[i].label}: ${data[i].value}${valueSuffix}`}</title>
          </circle>
        ))}
        {activePt && <line x1={activePt[0]} x2={activePt[0]} y1={padY} y2={h - padY} className="stroke-brand-400" strokeWidth={1.5} strokeDasharray="4 3" vectorEffect="non-scaling-stroke" />}
      </svg>
      {activePt && active !== null && (
        <>
          <span
            aria-hidden="true"
            className="pointer-events-none absolute h-3 w-3 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-aqua-400 bg-surface shadow"
            style={{ left: `${(activePt[0] / w) * 100}%`, top: `${(activePt[1] / h) * 100}%` }}
          />
          <div
            className="pointer-events-none absolute z-10 -translate-y-full whitespace-nowrap rounded-lg border border-surface-border bg-surface px-2.5 py-1.5 text-xs shadow-lg"
            style={{
              left: `${Math.min(88, Math.max(12, (activePt[0] / w) * 100))}%`,
              top: `calc(${(activePt[1] / h) * 100}% - 10px)`,
              transform: "translate(-50%, -100%)",
            }}
          >
            <span className="font-semibold text-gray-500">{data[active].label}</span>
            <span className="ml-2 font-bold tabular-nums text-heading">{data[active].value.toLocaleString()}{valueSuffix}</span>
          </div>
        </>
      )}
      </div>
      <div className="mt-1 flex justify-between text-[10px] text-gray-400">
        <span>{data[0]?.label}</span>
        {data.length > 2 && <span>{data[Math.floor(data.length / 2)]?.label}</span>}
        <span>{data[data.length - 1]?.label}</span>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Donut chart                                                         */
/* ------------------------------------------------------------------ */

export interface DonutSlice {
  label: string;
  value: number;
  color: string; // any CSS color
}

export function DonutChart({ slices, centerLabel, centerValue }: { slices: DonutSlice[]; centerLabel?: string; centerValue?: string | number }) {
  const total = slices.reduce((s, x) => s + x.value, 0);
  const r = 60;
  const c = 2 * Math.PI * r;
  let offset = 0;

  return (
    <div className="flex flex-wrap items-center gap-6">
      <svg viewBox="0 0 160 160" className="h-40 w-40 shrink-0 -rotate-90">
        <circle cx="80" cy="80" r={r} fill="none" className="stroke-surface-muted" strokeWidth={18} />
        {total > 0 &&
          slices.map((s) => {
            const len = (s.value / total) * c;
            const el = (
              <circle
                key={s.label}
                cx="80"
                cy="80"
                r={r}
                fill="none"
                stroke={s.color}
                strokeWidth={18}
                strokeDasharray={`${len} ${c - len}`}
                strokeDashoffset={-offset}
                strokeLinecap="butt"
              />
            );
            offset += len;
            return el;
          })}
      </svg>
      <div className="flex flex-col gap-2">
        {(centerValue !== undefined || centerLabel) && (
          <div className="mb-1">
            <div className="text-2xl font-semibold tabular-nums text-gray-900">{centerValue}</div>
            <div className="text-xs text-gray-500">{centerLabel}</div>
          </div>
        )}
        {slices.map((s) => (
          <div key={s.label} className="flex items-center gap-2 text-sm">
            <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: s.color }} />
            <span className="text-gray-600">{s.label}</span>
            <span className="ml-auto font-medium tabular-nums text-gray-900">{s.value}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Horizontal bar list                                                 */
/* ------------------------------------------------------------------ */

export interface BarItem {
  label: string;
  sub?: string;
  value: number;
  max: number;
  suffix?: string;
}

export function BarList({ items }: { items: BarItem[] }) {
  return (
    <div className="flex flex-col gap-3.5">
      {items.map((it, i) => {
        const pct = it.max > 0 ? Math.round((it.value / it.max) * 100) : 0;
        return (
          <div key={`${it.label}-${i}`}>
            <div className="mb-1 flex items-baseline justify-between gap-2 text-sm">
              <span className="truncate font-medium text-gray-800">{it.label}</span>
              <span className="shrink-0 tabular-nums text-gray-500">
                {it.value}
                {it.suffix ?? ""}
              </span>
            </div>
            <div className="h-2 w-full overflow-hidden rounded-full bg-surface-muted">
              <div className="h-full rounded-full bg-gradient-to-r from-brand-500 to-aqua-400 transition-[width]" style={{ width: `${pct}%` }} />
            </div>
            {it.sub && <p className="mt-0.5 text-xs text-gray-400">{it.sub}</p>}
          </div>
        );
      })}
    </div>
  );
}
