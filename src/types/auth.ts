export interface CurrentUser {
  id: string;
  employeeCode: string;
  fullName: string;
  email: string | null;
  organizationId: string;
  organizationSlug: string;
  platformSlug: string | null;
  platformLabel: string | null;
  regionId: string | null;
  regionName: string | null;
  permissions: string[];
  roles: string[];
  isAdmin: boolean;
}

export interface TokenPair {
  accessToken: string;
  refreshToken: string;
}
