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
  mustChangePassword: boolean;
  /** The server lets an Entry Contributor change an entry they already submitted (off by default). */
  canCorrectOwnEntries: boolean;
  /** entry_contributor | team_lead | entry_reviewer | administrator */
  entryLevel: string;
}

export interface TokenPair {
  accessToken: string;
}
