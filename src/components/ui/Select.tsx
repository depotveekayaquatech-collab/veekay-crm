import { forwardRef, type SelectHTMLAttributes } from "react";
import { IconChevronDown } from "@/components/ui/icons";

interface Option {
  value: string;
  label: string;
}

interface SelectProps extends SelectHTMLAttributes<HTMLSelectElement> {
  label: string;
  error?: string;
  options: Option[];
  placeholder?: string;
}

export const Select = forwardRef<HTMLSelectElement, SelectProps>(
  ({ label, error, options, placeholder, id, className = "", ...rest }, ref) => {
    const selectId = id ?? label.toLowerCase().replace(/\s+/g, "-");
    return (
      <div className="flex flex-col gap-1.5">
        <label htmlFor={selectId} className="text-sm font-medium text-gray-700">
          {label}
        </label>
        <div className="relative">
          <select
            id={selectId}
            ref={ref}
            aria-invalid={Boolean(error)}
            className={`h-10 w-full appearance-none rounded-md border bg-white pl-3 pr-9 text-sm text-gray-900 shadow-sm outline-none transition-colors focus:ring-2 disabled:cursor-not-allowed disabled:bg-surface-subtle ${
              error
                ? "border-status-danger focus:border-status-danger focus:ring-status-danger/20"
                : "border-surface-border focus:border-brand-500 focus:ring-brand-500/20"
            } ${className}`}
            {...rest}
          >
            {placeholder && <option value="">{placeholder}</option>}
            {options.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
          <IconChevronDown className="pointer-events-none absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" />
        </div>
        {error && <p className="text-sm text-status-danger">{error}</p>}
      </div>
    );
  },
);
Select.displayName = "Select";
