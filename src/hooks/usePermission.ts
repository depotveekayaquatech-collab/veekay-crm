import { useAuth } from "@/features/auth/useAuth";

/** Component-level permission gate — the frontend hides UI for a nicer
 * experience, but this NEVER replaces backend enforcement (require_permission
 * in api/deps.py is the real guard; see spec section 6). */
export function usePermission(permission: string): boolean {
  const { hasPermission } = useAuth();
  return hasPermission(permission);
}
