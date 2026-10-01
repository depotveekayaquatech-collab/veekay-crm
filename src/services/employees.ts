import { apiRequest } from "@/services/api";
import { mapPage, type Page, type PageWire } from "@/types/common";
import {
  toEmployee,
  type Employee,
  type EmployeeCreateInput,
  type EmployeeUpdateInput,
  type EmployeeWire,
  type PermissionGroup,
  type StateBoard,
} from "@/types/employee";

interface ListParams {
  page?: number;
  pageSize?: number;
  q?: string;
  regionId?: string;
  platformId?: string;
  category?: string;
}

export async function listEmployees(params: ListParams = {}): Promise<Page<Employee>> {
  const qs = new URLSearchParams();
  if (params.page) qs.set("page", String(params.page));
  if (params.pageSize) qs.set("page_size", String(params.pageSize));
  if (params.q) qs.set("q", params.q);
  if (params.regionId) qs.set("region_id", params.regionId);
  if (params.platformId) qs.set("platform_id", params.platformId);
  if (params.category) qs.set("category", params.category);
  const wire = await apiRequest<PageWire<EmployeeWire>>(`/employees?${qs}`);
  return mapPage(wire, toEmployee);
}

export async function createEmployee(input: EmployeeCreateInput): Promise<Employee> {
  return toEmployee(await apiRequest<EmployeeWire>("/employees", { method: "POST", body: input }));
}

export async function updateEmployee(id: string, input: EmployeeUpdateInput): Promise<Employee> {
  return toEmployee(await apiRequest<EmployeeWire>(`/employees/${id}`, { method: "PATCH", body: input }));
}

export async function deactivateEmployee(id: string): Promise<void> {
  await apiRequest(`/employees/${id}/deactivate`, { method: "POST" });
}

export async function setEmployeePermissions(id: string, codes: string[]): Promise<Employee> {
  return toEmployee(
    await apiRequest<EmployeeWire>(`/employees/${id}/permissions`, { method: "PUT", body: { codes } }),
  );
}

export async function setEmployeeScope(
  id: string,
  platformId: string | null,
  regionId: string | null,
): Promise<Employee> {
  return toEmployee(
    await apiRequest<EmployeeWire>(`/assignments/scope/${id}`, {
      method: "PUT",
      body: { platform_id: platformId, region_id: regionId },
    }),
  );
}

export function listPermissionGroups(): Promise<PermissionGroup[]> {
  return apiRequest<PermissionGroup[]>("/permissions");
}

export function getStateBoard(partner: string): Promise<StateBoard> {
  return apiRequest<StateBoard>(`/assignments/states?partner=${encodeURIComponent(partner)}`);
}

export async function assignState(partnerId: string, state: string, employeeId: string): Promise<void> {
  await apiRequest("/assignments/states", {
    method: "POST",
    body: { partner_id: partnerId, state, employee_id: employeeId },
  });
}

export async function unassignState(assignmentId: string): Promise<void> {
  await apiRequest(`/assignments/states/${assignmentId}`, { method: "DELETE" });
}
