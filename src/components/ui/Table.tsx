import type { ReactNode, ThHTMLAttributes, TdHTMLAttributes } from "react";
import { EmptyState } from "@/components/feedback/EmptyState";

/** Consistent list-table shell: horizontal scroll on small screens, so a
 * wide table never breaks the page layout. */
export function Table({ className = "", children }: { className?: string; children: ReactNode }) {
  return (
    <div className={`overflow-x-auto rounded-xl border border-surface-border bg-surface shadow-card ${className}`}>
      <table className="w-full min-w-[560px] border-collapse text-sm">{children}</table>
    </div>
  );
}

export function Th({ className = "", children, ...rest }: ThHTMLAttributes<HTMLTableCellElement> & { children?: ReactNode }) {
  return (
    <th
      className={`border-b border-surface-border bg-surface-subtle/80 px-4 py-3.5 text-left text-[11px] font-bold uppercase tracking-wider text-gray-500 select-none ${className}`}
      {...rest}
    >
      {children}
    </th>
  );
}

export function Td({ className = "", children, ...rest }: TdHTMLAttributes<HTMLTableCellElement> & { children?: ReactNode }) {
  return (
    <td className={`border-b border-surface-border/60 px-4 py-3.5 text-gray-700 transition-colors ${className}`} {...rest}>
      {children}
    </td>
  );
}

export function TableEmpty({
  colSpan,
  title = "No records found",
  description,
  children,
}: {
  colSpan: number;
  title?: string;
  description?: string;
  children?: ReactNode;
}) {
  const desc = description ?? (typeof children === "string" ? children : undefined);
  const action = children && typeof children !== "string" ? (
    <div className="mt-2 text-sm text-gray-500">{children}</div>
  ) : undefined;

  return (
    <tr>
      <td colSpan={colSpan} className="p-8">
        <EmptyState
          title={title}
          description={desc ?? (children ? undefined : "Try adjusting your filters or search query.")}
          action={action}
        />
      </td>
    </tr>
  );
}
