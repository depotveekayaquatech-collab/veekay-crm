import { Navigate } from "react-router-dom";
import { useAuth } from "@/features/auth/useAuth";
import { FullPageLoader } from "@/components/feedback/Skeleton";

/** Sends each user to the most useful landing page for what they can do. */
export function HomePage() {
  const { user, isLoading } = useAuth();
  if (isLoading) return <FullPageLoader />;
  if (!user) return <Navigate to="/login" replace />;

  const has = (p: string) => user.permissions.includes(p);
  const target = has("orders.overview")
    ? "/orders/overview"
    : has("orders.mark")
      ? "/orders"
      : has("stores.view")
        ? "/stores"
        : has("regions.view")
          ? "/regions"
          : has("activity.view")
            ? "/activity"
            : "/orders";
  return <Navigate to={target} replace />;
}
