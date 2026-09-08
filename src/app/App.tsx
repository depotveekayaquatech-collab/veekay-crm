import { BrowserRouter } from "react-router-dom";
import { AppProviders } from "@/app/providers";
import { AppRoutes } from "@/app/router";
import { ErrorBoundary } from "@/app/ErrorBoundary";
import { ToastHost } from "@/components/feedback/Toast";

export function App() {
  return (
    <ErrorBoundary>
      <AppProviders>
        <BrowserRouter>
          <AppRoutes />
          <ToastHost />
        </BrowserRouter>
      </AppProviders>
    </ErrorBoundary>
  );
}
