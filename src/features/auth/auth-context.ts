import { createContext } from "react";
import type { CurrentUser } from "@/types/auth";

export interface AuthContextValue {
  user: CurrentUser | null;
  isLoading: boolean;
  login: (
    organizationSlug: string,
    employeeCode: string,
    password: string,
    afterSignIn?: () => Promise<void>,
  ) => Promise<void>;
  logout: () => Promise<void>;
  changePassword: (currentPassword: string, newPassword: string) => Promise<void>;
  hasPermission: (permission: string) => boolean;
  hasRole: (role: string) => boolean;
}

export const AuthContext = createContext<AuthContextValue | undefined>(undefined);
