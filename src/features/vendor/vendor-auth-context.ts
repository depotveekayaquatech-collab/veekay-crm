import { createContext, useContext } from "react";
import type { Me } from "@/features/vendor/vendorApi";

export interface VendorAuthValue {
  account: Me | null;
  isLoading: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
}

export const VendorAuthContext = createContext<VendorAuthValue | undefined>(undefined);

export function useVendorAuth(): VendorAuthValue {
  const ctx = useContext(VendorAuthContext);
  if (!ctx) throw new Error("useVendorAuth must be used within VendorAuthProvider");
  return ctx;
}
