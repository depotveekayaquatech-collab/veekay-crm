/**
 * Minimal global toast bus — no context provider needed to fire one,
 * so services/api.ts (outside the React tree) can push errors here
 * the same way it pushes session-expiry via services/api.ts's
 * setOnSessionExpired. ToastHost (components/feedback/Toast.tsx)
 * subscribes and renders whatever's in the queue.
 */
export type ToastVariant = "error" | "success" | "info";

export interface Toast {
  id: string;
  message: string;
  variant: ToastVariant;
}

type Listener = (toasts: Toast[]) => void;

let toasts: Toast[] = [];
const listeners = new Set<Listener>();

function emit() {
  listeners.forEach((listener) => listener(toasts));
}

export function subscribeToasts(listener: Listener): () => void {
  listeners.add(listener);
  listener(toasts);
  return () => listeners.delete(listener);
}

const MAX_VISIBLE = 3;
const timers = new Map<string, ReturnType<typeof setTimeout>>();

export function pushToast(message: string, variant: ToastVariant = "error") {
  // An identical toast that is already showing is kept (and its timer restarted) instead of stacking a copy:
  // one page can fire a dozen requests that all fail for the same reason.
  const existing = toasts.find((t) => t.message === message && t.variant === variant);
  if (existing) {
    clearTimeout(timers.get(existing.id));
    timers.set(existing.id, setTimeout(() => dismissToast(existing.id), 5000));
    return;
  }
  const toast: Toast = { id: crypto.randomUUID(), message, variant };
  toasts = [...toasts, toast].slice(-MAX_VISIBLE);
  emit();
  timers.set(toast.id, setTimeout(() => dismissToast(toast.id), 5000));
}

export function dismissToast(id: string) {
  clearTimeout(timers.get(id));
  timers.delete(id);
  toasts = toasts.filter((t) => t.id !== id);
  emit();
}
