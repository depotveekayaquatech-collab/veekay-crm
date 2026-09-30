import { useState } from "react";
import { PageHeader } from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Pagination } from "@/components/ui/Pagination";
import { Table, Td, Th, TableEmpty } from "@/components/ui/Table";
import { Skeleton } from "@/components/feedback/Skeleton";
import { ErrorState } from "@/components/feedback/ErrorState";
import { IconPlus, IconUpload } from "@/components/ui/icons";
import { ImportEmployeesModal } from "@/features/team/ImportEmployeesModal";
import { ResetPasswordModal } from "@/features/team/ResetPasswordModal";
import { usePermission } from "@/hooks/usePermission";
import { EmployeeAccessModal } from "@/features/team/EmployeeAccessModal";
import { StateBoardPanel } from "@/features/team/StateBoardPanel";
import { useEmployees, useTeamMutations } from "@/features/team/useTeam";
import type { Employee } from "@/types/employee";

export function TeamPage() {
  const [page, setPage] = useState(1);
  const [q, setQ] = useState("");
  const [editing, setEditing] = useState<Employee | null | undefined>(undefined);
  const [importing, setImporting] = useState(false);
  const [resetting, setResetting] = useState<Employee | null>(null);
  const canReset = usePermission("employees.update");

  const canCreate = usePermission("employees.create");
  const canAssign = usePermission("assignments.manage");
  const canDeactivate = usePermission("employees.deactivate");
  const { deactivate } = useTeamMutations();
  const { data, isLoading, isError, refetch } = useEmployees(page, q);

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Team & access"
        subtitle="Employee IDs, platform / region scope, and what each person can see."
        action={
          canCreate && (
            <div className="flex flex-wrap gap-2">
              <Button variant="secondary" onClick={() => setImporting(true)}>
                <IconUpload className="h-4 w-4" /> Import employees
              </Button>
              <Button onClick={() => setEditing(null)}>
                <IconPlus className="h-4 w-4" /> New employee
              </Button>
            </div>
          )
        }
      />

      <Input
        label="Search"
        value={q}
        onChange={(e) => { setQ(e.target.value); setPage(1); }}
        placeholder="ID, name or email"
        className="sm:max-w-xs"
      />

      {isLoading && <Skeleton className="h-64" />}
      {isError && <ErrorState message="Couldn't load the team." onRetry={() => refetch()} />}

      {data && (
        <>
          <Table>
            <thead>
              <tr>
                <Th>Employee ID</Th>
                <Th>Name</Th>
                <Th>Platform</Th>
                <Th>Scope</Th>
                <Th>Permissions</Th>
                <Th>Status</Th>
                {(canCreate || canDeactivate || canReset) && <Th className="text-right">Actions</Th>}
              </tr>
            </thead>
            <tbody>
              {data.items.length === 0 && <TableEmpty colSpan={7}>No employees yet.</TableEmpty>}
              {data.items.map((e) => (
                <tr key={e.id}>
                  <Td className="font-medium text-gray-900">{e.employeeCode}</Td>
                  <Td>{e.fullName}</Td>
                  <Td>{e.platformSlug ?? "—"}</Td>
                  <Td>{e.regionName ?? (e.states.length ? e.states.join(", ") : "—")}</Td>
                  <Td>{e.directPermissions.length}</Td>
                  <Td>
                    <Badge tone={e.isActive ? "success" : "neutral"}>{e.isActive ? "Active" : "Deactivated"}</Badge>
                  </Td>
                  {(canCreate || canDeactivate || canReset) && (
                    <Td className="text-right">
                      <div className="flex justify-end gap-3 text-sm font-medium">
                        {canCreate && (
                          <button className="text-brand-600 hover:text-brand-700" onClick={() => setEditing(e)}>
                            Edit
                          </button>
                        )}
                        {canReset && e.isActive && (
                          <button className="text-brand-600 hover:text-brand-700" onClick={() => setResetting(e)}>
                            Reset password
                          </button>
                        )}
                        {canDeactivate && e.isActive && (
                          <button
                            className="text-status-danger hover:underline"
                            onClick={() => confirm(`Deactivate ${e.fullName}?`) && deactivate.mutate(e.id)}
                          >
                            Deactivate
                          </button>
                        )}
                      </div>
                    </Td>
                  )}
                </tr>
              ))}
            </tbody>
          </Table>
          <Pagination page={data.page} pageSize={data.pageSize} total={data.total} onPageChange={setPage} />
        </>
      )}

      {canAssign && <StateBoardPanel />}

      {editing !== undefined && (
        <EmployeeAccessModal key={editing?.id ?? "new"} onClose={() => setEditing(undefined)} employee={editing ?? null} />
      )}
      {importing && <ImportEmployeesModal onClose={() => setImporting(false)} />}
      {resetting && <ResetPasswordModal employee={resetting} onClose={() => setResetting(null)} />}
    </div>
  );
}
