import type { ReactNode } from "react";

export function EmptyState({
  title,
  description,
  action,
}: {
  title: string;
  description?: string;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-1.5 rounded-lg border border-dashed border-surface-border bg-surface-subtle/50 px-6 py-12 text-center">
      <p className="text-sm font-semibold text-gray-800">{title}</p>
      {description && <p className="max-w-xs text-sm text-gray-500">{description}</p>}
      {action && <div className="mt-3">{action}</div>}
    </div>
  );
}
