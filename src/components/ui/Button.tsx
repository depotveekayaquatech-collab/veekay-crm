import type { ButtonHTMLAttributes } from "react";

type Variant = "primary" | "secondary" | "danger" | "ghost";
type Size = "sm" | "md" | "lg";

const variantClasses: Record<Variant, string> = {
  primary:
    "bg-brand-600 text-white hover:bg-brand-700 active:bg-brand-800 border border-transparent disabled:opacity-55",
  secondary:
    "bg-surface text-gray-800 border border-surface-border hover:border-gray-400 hover:bg-surface-subtle disabled:opacity-55",
  danger:
    "bg-status-danger text-white hover:brightness-90 active:brightness-75 border border-transparent disabled:opacity-55",
  ghost:
    "bg-transparent text-gray-700 hover:bg-surface-subtle hover:text-gray-900 disabled:opacity-55",
};

const sizeClasses: Record<Size, string> = {
  // 32 / 40 / 44px on a mouse; every size is 44px tall on a touch screen so a thumb can hit it.
  sm: "h-8 px-3 text-xs gap-1.5 [@media(pointer:coarse)]:h-11 [@media(pointer:coarse)]:text-sm",
  md: "h-10 px-4 text-sm gap-2 [@media(pointer:coarse)]:h-11",
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
        <span aria-hidden="true" className="h-3.5 w-3.5 animate-spin motion-reduce:animate-none rounded-full border-2 border-current border-t-transparent" />
      )}
      {children}
    </button>
  );
}
