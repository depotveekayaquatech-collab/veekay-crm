import type { ButtonHTMLAttributes } from "react";

type Variant = "primary" | "secondary" | "danger" | "ghost";
type Size = "sm" | "md" | "lg";

const variantClasses: Record<Variant, string> = {
  primary:
    "bg-gradient-to-r from-brand-600 via-brand-500 to-brand-600 hover:from-brand-500 hover:via-brand-500 hover:to-aqua-500 text-white shadow-sm hover:shadow-glow active:scale-[0.98] border border-white/15 disabled:opacity-50 disabled:shadow-none",
  secondary:
    "bg-surface text-gray-800 border border-surface-border shadow-xs hover:border-gray-400 hover:bg-surface-subtle active:scale-[0.98] disabled:opacity-50 disabled:text-gray-400",
  danger:
    "bg-gradient-to-r from-rose-600 to-rose-500 hover:from-rose-500 hover:to-rose-600 text-white shadow-xs active:scale-[0.98] border border-rose-400/20 disabled:opacity-50",
  ghost:
    "bg-transparent text-gray-700 hover:bg-surface-subtle hover:text-gray-900 active:scale-[0.98]",
};

const sizeClasses: Record<Size, string> = {
  sm: "h-8 px-3 text-xs gap-1.5",
  md: "h-10 px-4 text-sm gap-2",
  lg: "h-11 px-5 text-sm gap-2",
};

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  isLoading?: boolean;
  fullWidth?: boolean;
}

export function Button({
  variant = "primary",
  size = "md",
  isLoading,
  fullWidth,
  className = "",
  children,
  disabled,
  ...rest
}: ButtonProps) {
  return (
    <button
      className={`inline-flex select-none items-center justify-center whitespace-nowrap rounded-lg font-semibold transition-[color,background-color,border-color,box-shadow,transform,filter] duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2 disabled:cursor-not-allowed ${
        fullWidth ? "w-full" : ""
      } ${sizeClasses[size]} ${variantClasses[variant]} ${className}`}
      disabled={disabled || isLoading}
      aria-busy={isLoading || undefined}
      {...rest}
    >
      {isLoading && (
        <span aria-hidden="true" className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-current border-t-transparent" />
      )}
      {children}
    </button>
  );
}
