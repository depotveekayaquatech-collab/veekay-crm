import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  assignState,
  createEmployee,
  deactivateEmployee,
  getStateBoard,
  listEmployees,
  listPermissionGroups,
  setAdminAccess,
  setEmployeePermissions,
  setEmployeeScope,
  type ScopeInput,
  unassignState,
  updateEmployee,
} from "@/services/employees";
import { pushToast } from "@/lib/toast";
import type { EmployeeCreateInput, EmployeeUpdateInput } from "@/types/employee";

export function useEmployees(page: number, q: string, category = "") {
  return useQuery({
    queryKey: ["employees", page, q, category],
    queryFn: () => listEmployees({ page, pageSize: 20, q: q.trim() || undefined, category: category || undefined }),
  });
}

export function usePermissionGroups() {
  return useQuery({ queryKey: ["permission-groups"], queryFn: listPermissionGroups, staleTime: 300_000 });
}

export function useStateBoard(partner: string) {
  return useQuery({
    queryKey: ["state-board", partner],
    queryFn: () => getStateBoard(partner),
    enabled: Boolean(partner),
  });
}

export function useTeamMutations() {
  const qc = useQueryClient();
  const done = (msg: string) => {
    qc.invalidateQueries({ queryKey: ["employees"] });
    qc.invalidateQueries({ queryKey: ["state-board"] });
    pushToast(msg, "success");
  };

  return {
    create: useMutation({
      mutationFn: (input: EmployeeCreateInput) => createEmployee(input),
      onSuccess: () => done("Employee created."),
    }),
    update: useMutation({
      mutationFn: ({ id, input }: { id: string; input: EmployeeUpdateInput }) => updateEmployee(id, input),
      onSuccess: () => done("Employee updated."),
    }),
    deactivate: useMutation({
      mutationFn: (id: string) => deactivateEmployee(id),
      onSuccess: () => done("Employee deactivated."),
    }),
    setAdminAccess: useMutation({
      mutationFn: ({ id, full }: { id: string; full: boolean }) => setAdminAccess(id, full),
      onSuccess: () => done("Admin access updated."),
    }),
    setPermissions: useMutation({
      mutationFn: ({ id, codes }: { id: string; codes: string[] }) => setEmployeePermissions(id, codes),
      onSuccess: () => done("Permissions saved."),
    }),
    setScope: useMutation({
      mutationFn: ({ id, ...scope }: { id: string } & ScopeInput) => setEmployeeScope(id, scope),
      onSuccess: () => done("Scope saved."),
    }),
    assignState: useMutation({
      mutationFn: ({ partnerId, state, employeeId }: { partnerId: string; state: string; employeeId: string }) =>
        assignState(partnerId, state, employeeId),
      onSuccess: () => done("State assigned."),
    }),
    unassignState: useMutation({
      mutationFn: (assignmentId: string) => unassignState(assignmentId),
      onSuccess: () => done("State unassigned."),
    }),
  };
}
