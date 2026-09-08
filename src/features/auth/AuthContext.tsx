import { createContext, useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { fetchCurrentUser, login as loginRequest, logout as logoutRequest } from "@/services/auth";
import { getPersistedRefreshToken, setOnSessionExpired, setTokens } from "@/services/api";
import type { CurrentUser } from "@/types/auth";

interface AuthContextValue {
  user: CurrentUser | null;
  isLoading: boolean;
  login: (organizationSlug: string, email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  hasPermission: (permission: string) => boolean;
  hasRole: (role: string) => boolean;
}

export const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    setOnSessionExpired(() => setUser(null));

    // Session restore on load: if a refresh token survived a page reload,
    // silently exchange it for a fresh access token and re-fetch /auth/me
    // rather than dropping the person back to the login screen every time
    // they hit F5. `silent: true` on fetchCurrentUser suppresses the error
    // toast for the common, expected case of "no session yet".
    async function restore() {
      const persisted = getPersistedRefreshToken();
      if (!persisted) {
        setIsLoading(false);
        return;
      }
      try {
        setTokens({ accessToken: "", refreshToken: persisted }); // seed refresh; apiRequest will 401-refresh once
        const currentUser = await fetchCurrentUser(true);
        setUser(currentUser);
      } catch {
        setTokens(null);
      } finally {
        setIsLoading(false);
      }
    }
    void restore();
  }, []);

  const login = useCallback(async (organizationSlug: string, email: string, password: string) => {
    const currentUser = await loginRequest({ organizationSlug, email, password });
    setUser(currentUser);
  }, []);

  const logout = useCallback(async () => {
    await logoutRequest();
    setUser(null);
  }, []);

  const hasPermission = useCallback(
    (permission: string) => user?.permissions.includes(permission) ?? false,
    [user],
  );

  const hasRole = useCallback((role: string) => user?.roles.includes(role) ?? false, [user]);

  const value = useMemo(
    () => ({ user, isLoading, login, logout, hasPermission, hasRole }),
    [user, isLoading, login, logout, hasPermission, hasRole],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
