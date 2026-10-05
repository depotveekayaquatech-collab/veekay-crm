import { useEffect, useState } from "react";
import { dismissToast, subscribeToasts, type Toast, type ToastVariant } from "@/lib/toast";
import { IconAlertTriangle, IconCheckCircle, IconClose, IconInfo } from "@/components/ui/icons";

const variantMeta: Record<ToastVariant, { accent: string; icon: typeof IconInfo }> = {
  error: { accent: "text-status-danger", icon: IconAlertTriangle },
  success: { accent: "text-status-success", icon: IconCheckCircle },
  info: { accent: "text-status-info", icon: IconInfo },
};

/** Mount once near the root (see app/App.tsx). Renders whatever's in the
 * global toast queue — nothing else needs a provider to push a toast. */
export function ToastHost() {
  const [toasts, setToasts] = useState<Toast[]>([]);

  useEffect(() => subscribeToasts(setToasts), []);

  if (toasts.length === 0) return null;

  return (
    <div className="pointer-events-none fixed inset-x-4 bottom-4 z-50 flex flex-col gap-2 sm:inset-x-auto sm:right-4 sm:w-80">
      {toasts.map((toast) => {
        const { accent, icon: Icon } = variantMeta[toast.variant];
        return (
          <div
            key={toast.id}
            role="alert"
            className="pointer-events-auto flex animate-slide-up items-start gap-3 rounded-lg border border-surface-border bg-surface p-3 text-sm shadow-lg"
          >
            <Icon className={`mt-0.5 h-4 w-4 shrink-0 ${accent}`} />
            <span className="flex-1 text-gray-800">{toast.message}</span>
            <button
              onClick={() => dismissToast(toast.id)}
              aria-label="Dismiss"
              className="shrink-0 rounded p-0.5 text-gray-400 transition-colors hover:text-gray-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500"
            >
              <IconClose className="h-4 w-4" />
            </button>
          </div>
        );
      })}
    </div>
  );
}
