import { Component, type ErrorInfo, type ReactNode } from "react";
import { Button } from "@/components/ui/Button";

interface Props {
  children: ReactNode;
}

interface State {
  error: Error | null;
}

/** Catches render-time crashes anywhere below it so one broken component
 * doesn't blank the whole app. Does NOT catch errors from event handlers
 * or async code (React limitation) — those go through services/api.ts's
 * toast path instead. Never shows the raw stack trace to the user
 * (spec section 23). */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("Unhandled error in component tree:", error, info.componentStack);
  }

  render() {
    if (this.state.error) {
      return (
        <div className="flex min-h-screen items-center justify-center bg-surface-subtle p-6">
          <div className="w-full max-w-sm rounded-lg border border-surface-border bg-surface p-8 text-center shadow-card">
            <h1 className="text-lg font-semibold text-gray-900">Something went wrong</h1>
            <p className="mt-2 text-sm text-gray-500">
              An unexpected error occurred. Reloading usually fixes this.
            </p>
            <Button className="mt-6" onClick={() => window.location.reload()}>
              Reload
            </Button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
