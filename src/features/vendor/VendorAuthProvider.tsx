import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { VendorAuthContext } from "@/features/vendor/vendor-auth-context";
import { hasVendorHint, refreshVendorToken, setOnVendorExpired, setVendorToken, vendorApi, type Me } from "@/features/vendor/vendorApi";

export function VendorAuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const [account, setAccount] = useState<Me | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    setOnVendorExpired(() => setAccount(null));
    // Restore after a reload: the refresh token is an HttpOnly cookie, so just ask for a new access token.
    async function restore() {
      if (hasVendorHint()) {
        try {
          if (await refreshVendorToken()) setAccount(await vendorApi.me());
        } catch {
          setVendorToken(null);
        }
      }
      setIsLoading(false);
    }
    void restore();
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    await vendorApi.login(email.trim(), password);
    setAccount(await vendorApi.me());
  }, []);

  const logout = useCallback(async () => {
    await vendorApi.logout();
    setAccount(null);
    queryClient.removeQueries({ queryKey: ["vendor"] });
  }, [queryClient]);

  const value = useMemo(() => ({ account, isLoading, login, logout }), [account, isLoading, login, logout]);
  return <VendorAuthContext.Provider value={value}>{children}</VendorAuthContext.Provider>;
}
