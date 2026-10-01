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
  states: string[];
  roles: string[];
  category: "admin" | "accounts" | "blinkit" | "zepto" | "other";
  categoryLabel: string;
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
  states: string[];
  roles: string[];
  category?: "admin" | "accounts" | "blinkit" | "zepto" | "other";
  category_label?: string;
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
    states: w.states,
    roles: w.roles,
    category: w.category ?? "other",
    categoryLabel: w.category_label ?? "",
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
