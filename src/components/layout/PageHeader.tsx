import type { ReactNode } from "react";

export function PageHeader({
  title,
  subtitle,
  badge,
  action,
}: {
  title: string;
  subtitle?: string;
  badge?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2.5">
          <h2 className="text-2xl font-extrabold tracking-tight text-heading sm:text-[1.75rem]">{title}</h2>
          {badge}
        </div>
        {subtitle && <p className="mt-1 text-sm text-gray-500 leading-relaxed max-w-3xl">{subtitle}</p>}
      </div>
      {action && <div className="flex flex-wrap items-center gap-2.5 shrink-0">{action}</div>}
    </div>
  );
}
