import type { ReactNode } from "react";

type Tone = "success" | "warning" | "danger" | "info" | "neutral";

const toneClasses: Record<Tone, { badge: string; dot: string }> = {
  success: {
    badge: "bg-emerald-500/10 text-emerald-700 dark:text-emerald-300 ring-1 ring-inset ring-emerald-500/25",
    dot: "bg-emerald-500",
  },
  warning: {
    badge: "bg-amber-500/10 text-amber-800 dark:text-amber-300 ring-1 ring-inset ring-amber-500/25",
    dot: "bg-amber-500",
  },
  danger: {
    badge: "bg-rose-500/10 text-rose-700 dark:text-rose-300 ring-1 ring-inset ring-rose-500/25",
    dot: "bg-rose-500",
  },
  info: {
    badge: "bg-sky-500/10 text-sky-700 dark:text-sky-300 ring-1 ring-inset ring-sky-500/25",
    dot: "bg-sky-500",
  },
  neutral: {
    badge: "bg-surface-muted text-gray-700 ring-1 ring-inset ring-surface-border",
    dot: "bg-gray-400",
  },
};

export function Badge({
  tone = "neutral",
  dot = false,
  className = "",
  children,
}: {
  tone?: Tone;
  dot?: boolean;
  className?: string;
  children: ReactNode;
}) {
  const t = toneClasses[tone];
  return (
    <span
      className={`inline-flex items-center gap-1.5 whitespace-nowrap rounded-full px-2.5 py-0.5 text-xs font-semibold leading-5 ${t.badge} ${className}`}
    >
      {dot && <span className={`h-1.5 w-1.5 rounded-full ${t.dot}`} aria-hidden="true" />}
      {children}
    </span>
  );
}
