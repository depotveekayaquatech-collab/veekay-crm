import type { ComponentType, ReactNode, SVGProps } from "react";
import { IconInbox } from "@/components/ui/icons";

export function EmptyState({
  title,
  description,
  action,
  icon: Icon = IconInbox,
}: {
  title: string;
  description?: string;
  action?: ReactNode;
  icon?: ComponentType<SVGProps<SVGSVGElement>>;
}) {
  return (
    <div className="flex flex-col items-center justify-center rounded-2xl border border-dashed border-surface-border bg-surface/60 px-6 py-12 text-center backdrop-blur-xs">
      <div className="mb-3.5 flex h-12 w-12 items-center justify-center rounded-2xl bg-brand-500/10 text-brand-500 ring-8 ring-brand-500/5 dark:bg-brand-500/15 dark:ring-brand-500/10">
        <Icon className="h-6 w-6" aria-hidden="true" />
      </div>
      <p className="text-sm font-bold text-heading">{title}</p>
      {description && <p className="mt-1 max-w-sm text-xs text-gray-500 leading-relaxed">{description}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}
