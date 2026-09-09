/**
 * Dependency-free SVG charts. Kept tiny and presentational — all data
 * shaping happens in the caller. Matches the icon set's "one visual
 * language, no libraries" approach.
 */
import { useId } from "react";

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
}: {
  data: AreaPoint[];
  height?: number;
  valueSuffix?: string;
}) {
  const gradientId = useId();
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

  return (
    <div className="w-full">
      <svg viewBox={`0 0 ${w} ${h}`} className="w-full" preserveAspectRatio="none" role="img" aria-label="Trend chart">
        <defs>
          <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="rgb(47 111 237)" stopOpacity="0.22" />
            <stop offset="100%" stopColor="rgb(47 111 237)" stopOpacity="0" />
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
        <path d={line} fill="none" className="stroke-brand-500" strokeWidth={2.5} strokeLinejoin="round" strokeLinecap="round" />
        {pts.map(([x, y], i) => (
          <circle key={i} cx={x} cy={y} r={data.length > 20 ? 0 : 3} className="fill-white stroke-brand-500" strokeWidth={2}>
            <title>{`${data[i].label}: ${data[i].value}${valueSuffix}`}</title>
          </circle>
        ))}
      </svg>
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
      {items.map((it) => {
        const pct = it.max > 0 ? Math.round((it.value / it.max) * 100) : 0;
        return (
          <div key={it.label}>
            <div className="mb-1 flex items-baseline justify-between gap-2 text-sm">
              <span className="truncate font-medium text-gray-800">{it.label}</span>
              <span className="shrink-0 tabular-nums text-gray-500">
                {it.value}
                {it.suffix ?? ""}
              </span>
            </div>
            <div className="h-2 w-full overflow-hidden rounded-full bg-surface-muted">
              <div className="h-full rounded-full bg-brand-500 transition-all" style={{ width: `${pct}%` }} />
            </div>
            {it.sub && <p className="mt-0.5 text-xs text-gray-400">{it.sub}</p>}
          </div>
        );
      })}
    </div>
  );
}
