import { createContext } from "react";
import type { CurrentUser } from "@/types/auth";

export interface AuthContextValue {
  user: CurrentUser | null;
  isLoading: boolean;
  login: (organizationSlug: string, employeeCode: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  hasPermission: (permission: string) => boolean;
  hasRole: (role: string) => boolean;
}

export const AuthContext = createContext<AuthContextValue | undefined>(undefined);
