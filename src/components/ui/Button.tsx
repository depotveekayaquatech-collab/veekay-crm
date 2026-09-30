import type { ButtonHTMLAttributes } from "react";

type Variant = "primary" | "secondary" | "danger" | "ghost";
type Size = "sm" | "md" | "lg";

const variantClasses: Record<Variant, string> = {
  primary:
    "bg-gradient-to-b from-brand-500 to-brand-600 text-white shadow-[0_1px_2px_rgba(11,18,34,0.2),inset_0_1px_0_rgba(255,255,255,0.18)] hover:from-brand-500 hover:to-brand-700 hover:shadow-glow active:translate-y-px disabled:from-brand-300 disabled:to-brand-300 disabled:shadow-none",
  secondary:
    "bg-white text-gray-800 border border-surface-border shadow-sm hover:border-gray-300 hover:bg-surface-subtle active:bg-surface-muted disabled:text-gray-400",
  danger:
    "bg-status-danger text-white shadow-sm hover:brightness-95 active:brightness-90 disabled:opacity-50",
  ghost: "bg-transparent text-gray-600 hover:bg-surface-subtle hover:text-gray-900 active:bg-surface-muted",
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
      className={`inline-flex select-none items-center justify-center whitespace-nowrap rounded-lg font-semibold transition-all duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2 disabled:cursor-not-allowed ${
        fullWidth ? "w-full" : ""
      } ${sizeClasses[size]} ${variantClasses[variant]} ${className}`}
      disabled={disabled || isLoading}
      aria-busy={isLoading || undefined}
      {...rest}
    >
      {isLoading && (
        <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-current border-t-transparent" />
      )}
      {children}
    </button>
  );
}
