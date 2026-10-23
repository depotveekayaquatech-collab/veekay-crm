import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { api, type Me } from "@/api/api";
import { ApiError, clearSession, refreshSession, setOnSessionExpired, signInPartner, signInStaff, signOut as endSession, storedSessionKind } from "@/api/client";
import { staffApi, type StaffMe } from "@/api/staff";
import { unregisterPush } from "@/lib/push";
import { setQueueOwner } from "@/lib/scanQueue";

interface AuthValue {
  /** A signed-in vendor or POC (null for anyone else). */
  account: Me | null;
  /** A signed-in Veekay employee (null for anyone else). */
  staff: StaffMe | null;
  /** True until the stored session (if any) has been checked: keep the splash screen up meanwhile. */
  loading: boolean;
  /** An email signs in a vendor / POC; anything else is an Employee ID. */
  signIn: (identifier: string, password: string) => Promise<void>;
  signOut: () => Promise<void>;
  /** Re-reads the employee profile (after a password change). */
  reloadStaff: () => Promise<void>;
  hasPermission: (code: string) => boolean;
}

const AuthContext = createContext<AuthValue | undefined>(undefined);

export function useAuth(): AuthValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const [account, setAccount] = useState<Me | null>(null);
  const [staff, setStaff] = useState<StaffMe | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setOnSessionExpired(() => {
      setQueueOwner(null);                       // nobody is signed in: nothing waiting on this phone may be sent now
      setAccount(null);
      setStaff(null);
      queryClient.clear();
    });
    // Restore the previous sign-in. No network on launch is not a sign-out: the person just sees the sign-in screen
    // with their session intact, and the next launch with a connection restores it.
    (async () => {
      try {
        const kind = await storedSessionKind();
        if (kind && (await refreshSession())) {
          if (kind === "partner") setAccount(await api.me());
          else {
            const me = await staffApi.me();
            setQueueOwner(me.id);
            setStaff(me);
          }
        }
      } catch (e) {
        if (e instanceof ApiError && e.status === 401) await clearSession();
      } finally {
        setLoading(false);
      }
    })();
  }, [queryClient]);

  const signIn = useCallback(async (identifier: string, password: string) => {
    if (identifier.includes("@")) {
      await signInPartner(identifier, password);
      setAccount(await api.me());
    } else {
      setQueueOwner(null);                       // the previous person's scans must not be sent with this login
      await signInStaff(identifier, password);
      const me = await staffApi.me();
      setQueueOwner(me.id);
      setStaff(me);
    }
  }, []);

  const reloadStaff = useCallback(async () => {
    setStaff(await staffApi.me());
  }, []);

  const signOut = useCallback(async () => {
    setQueueOwner(null);                         // first: from now on nothing waiting on this phone is sent
    await unregisterPush();
    await endSession();
    queryClient.clear();
    setAccount(null);
    setStaff(null);
  }, [queryClient]);

  const hasPermission = useCallback((code: string) => !!staff && !staff.must_change_password && staff.permissions.includes(code), [staff]);

  const value = useMemo(
    () => ({ account, staff, loading, signIn, signOut, reloadStaff, hasPermission }),
    [account, staff, loading, signIn, signOut, reloadStaff, hasPermission],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
