export interface Employee {
  id: string;
  employeeCode: string;
  fullName: string;
  email: string | null;
  phone: string | null;
  status: string;
  isActive: boolean;
  platformId: string | null;
  platformSlug: string | null;
  regionId: string | null;
  regionName: string | null;
  /** Every region covered (the main one first). */
  regions: { id: string; name: string }[];
  excludedStates: string[];
  excludedCities: string[];
  /** Specific states / cities given on top of the regions (or on their own). */
  includedStates: string[];
  includedCities: string[];
  states: string[];
  roles: string[];
  category: "admin" | "accounts" | "partner" | "blinkit" | "zepto" | "other";
  categoryLabel: string;
  /** For admin accounts: "full" = every permission, "custom" = only what was ticked. */
  adminLevel: "full" | "custom" | null;
  directPermissions: string[];
}

export interface EmployeeWire {
  id: string;
  employee_code: string;
  full_name: string;
  email: string | null;
  phone: string | null;
  status: string;
  is_active: boolean;
  platform_id: string | null;
  platform_slug: string | null;
  region_id: string | null;
  region_name: string | null;
  regions?: { id: string; name: string }[];
  excluded_states?: string[];
  excluded_cities?: string[];
  included_states?: string[];
  included_cities?: string[];
  states: string[];
  roles: string[];
  category?: "admin" | "accounts" | "partner" | "blinkit" | "zepto" | "other";
  category_label?: string;
  admin_level?: "full" | "custom" | null;
  direct_permissions: string[];
}

export function toEmployee(w: EmployeeWire): Employee {
  return {
    id: w.id,
    employeeCode: w.employee_code,
    fullName: w.full_name,
    email: w.email,
    phone: w.phone,
    status: w.status,
    isActive: w.is_active,
    platformId: w.platform_id,
    platformSlug: w.platform_slug,
    regionId: w.region_id,
    regionName: w.region_name,
    regions: w.regions ?? (w.region_id && w.region_name ? [{ id: w.region_id, name: w.region_name }] : []),
    excludedStates: w.excluded_states ?? [],
    excludedCities: w.excluded_cities ?? [],
    includedStates: w.included_states ?? [],
    includedCities: w.included_cities ?? [],
    states: w.states,
    roles: w.roles,
    category: w.category ?? "other",
    categoryLabel: w.category_label ?? "",
    adminLevel: w.admin_level ?? null,
    directPermissions: w.direct_permissions,
  };
}

export interface EmployeeCreateInput {
  employee_code: string;
  full_name: string;
  password: string;
  email?: string | null;
  phone?: string | null;
  platform_id?: string | null;
  region_id?: string | null;
  permission_codes?: string[];
  /** "partner" creates a Blinkit / Zepto login (own platform only, limited permissions). */
  account_type?: "employee" | "partner" | "admin";
  /** With account_type "admin": "full" gets every permission, "custom" only permission_codes. */
  admin_access?: "full" | "custom";
}

export interface EmployeeUpdateInput {
  full_name?: string;
  email?: string | null;
  phone?: string | null;
  password?: string;
}

export interface PermissionItem {
  code: string;
  description: string;
}

export interface PermissionGroup {
  key: string;
  label: string;
  permissions: PermissionItem[];
}

export interface StateRow {
  state: string;
  region_name: string | null;
  store_count: number;
  assignment_id?: string;
  employee_id?: string;
  employee_name?: string;
}

export interface StateBoard {
  assigned: StateRow[];
  unassigned: StateRow[];
  employees: { id: string; name: string; employee_code: string }[];
  assigned_state_count: number;
  unassigned_state_count: number;
  assigned_store_count: number;
  unassigned_store_count: number;
}
