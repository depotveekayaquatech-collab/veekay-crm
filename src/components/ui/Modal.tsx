import { useEffect, type ReactNode } from "react";
import { IconClose } from "@/components/ui/icons";

interface ModalProps {
  open: boolean;
  onClose: () => void;
  title: string;
  description?: string;
  children: ReactNode;
  /** Rendered in the footer, right-aligned (e.g. Cancel + Save buttons). */
  footer?: ReactNode;
  size?: "sm" | "md";
}

export function Modal({ open, onClose, title, description, children, footer, size = "md" }: ModalProps) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = "";
    };
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center p-0 sm:items-center sm:p-4">
      <div className="absolute inset-0 animate-fade-in bg-gray-900/40" onClick={onClose} aria-hidden="true" />
      <div
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className={`relative flex max-h-[92vh] w-full animate-slide-up flex-col rounded-t-xl bg-white shadow-lg sm:rounded-xl ${
          size === "sm" ? "sm:max-w-sm" : "sm:max-w-lg"
        }`}
      >
        <div className="flex items-start justify-between gap-4 border-b border-surface-border px-5 py-4">
          <div>
            <h2 className="text-sm font-semibold text-gray-900">{title}</h2>
            {description && <p className="mt-0.5 text-xs text-gray-500">{description}</p>}
          </div>
          <button
            onClick={onClose}
            aria-label="Close"
            className="-mr-1 -mt-1 rounded-md p-1.5 text-gray-400 hover:bg-surface-subtle hover:text-gray-700"
          >
            <IconClose className="h-5 w-5" />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-5 py-4">{children}</div>

        {footer && (
          <div className="flex justify-end gap-2 border-t border-surface-border px-5 py-3.5">{footer}</div>
        )}
      </div>
    </div>
  );
}
