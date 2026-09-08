export interface CurrentUser {
  id: string;
  fullName: string;
  email: string;
  organizationId: string;
  organizationSlug: string;
  permissions: string[];
  /** Role codes, e.g. "admin", "employee", "blinkit_admin" — used only
   * to decide which dashboard variant to render (see features/dashboard).
   * Every actual access-control decision still goes through `permissions`,
   * never a role name — see spec section 6. */
  roles: string[];
}

export interface TokenPair {
  accessToken: string;
  refreshToken: string;
}
