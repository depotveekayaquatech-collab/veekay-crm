import { forwardRef, type InputHTMLAttributes, type ReactNode } from "react";

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label: string;
  error?: string;
  hint?: string;
  /** Rendered inside the field on the right — e.g. a show/hide password toggle. */
  rightSlot?: ReactNode;
}

export const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ label, error, hint, rightSlot, id, className = "", ...rest }, ref) => {
    const inputId = id ?? label.toLowerCase().replace(/\s+/g, "-");
    const describedBy =
      [error ? `${inputId}-error` : null, hint && !error ? `${inputId}-hint` : null]
        .filter(Boolean)
        .join(" ") || undefined;

    return (
      <div className="flex flex-col gap-1.5">
        <label htmlFor={inputId} className="text-[13px] font-semibold text-gray-700">
          {label}
        </label>
        <div className="relative">
          <input
            id={inputId}
            ref={ref}
            aria-invalid={Boolean(error)}
            aria-describedby={describedBy}
            className={`h-10 w-full rounded-lg border bg-surface px-3.5 text-sm text-gray-900 shadow-sm outline-none transition-colors placeholder:text-gray-400 focus:ring-2 disabled:cursor-not-allowed disabled:bg-surface-subtle disabled:text-gray-500 ${
              error
                ? "border-status-danger focus:border-status-danger focus:ring-status-danger/20"
                : "border-surface-border focus:border-brand-500 focus:ring-brand-500/20"
            } ${rightSlot ? "pr-11" : ""} ${className}`}
            {...rest}
          />
          {rightSlot && (
            <div className="absolute inset-y-0 right-0 flex items-center pr-1.5">{rightSlot}</div>
          )}
        </div>
        {hint && !error && (
          <p id={`${inputId}-hint`} className="text-xs text-gray-500">
            {hint}
          </p>
        )}
        {error && (
          <p id={`${inputId}-error`} className="text-sm text-status-danger">
            {error}
          </p>
        )}
      </div>
    );
  },
);
Input.displayName = "Input";
