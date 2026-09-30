import type { ReactNode, ThHTMLAttributes, TdHTMLAttributes } from "react";

/** Consistent list-table shell: horizontal scroll on small screens, so a
 * wide table never breaks the page layout. */
export function Table({ children }: { children: ReactNode }) {
  return (
    <div className="overflow-x-auto rounded-xl border border-surface-border bg-white shadow-card">
      <table className="w-full min-w-[560px] border-collapse text-sm">{children}</table>
    </div>
  );
}

export function Th({ className = "", children, ...rest }: ThHTMLAttributes<HTMLTableCellElement> & { children?: ReactNode }) {
  return (
    <th
      className={`border-b border-surface-border bg-surface-subtle px-4 py-3 text-left text-[11px] font-bold uppercase tracking-wider text-gray-500 ${className}`}
      {...rest}
    >
      {children}
    </th>
  );
}

export function Td({ className = "", children, ...rest }: TdHTMLAttributes<HTMLTableCellElement> & { children?: ReactNode }) {
  return (
    <td className={`border-b border-surface-border px-4 py-3.5 text-gray-700 ${className}`} {...rest}>
      {children}
    </td>
  );
}

export function TableEmpty({ colSpan, children }: { colSpan: number; children: ReactNode }) {
  return (
    <tr>
      <td colSpan={colSpan} className="px-4 py-10 text-center text-sm text-gray-500">
        {children}
      </td>
    </tr>
  );
}
