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

export function pushToast(message: string, variant: ToastVariant = "error") {
  const toast: Toast = { id: crypto.randomUUID(), message, variant };
  toasts = [...toasts, toast];
  emit();
  setTimeout(() => dismissToast(toast.id), 5000);
}

export function dismissToast(id: string) {
  toasts = toasts.filter((t) => t.id !== id);
  emit();
}
