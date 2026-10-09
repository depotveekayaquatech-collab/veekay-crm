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
import { AdminAccountModal } from "@/features/team/AdminAccountModal";
import { useAuth } from "@/features/auth/useAuth";
import { PartnerAccountModal } from "@/features/team/PartnerAccountModal";
import { LoginsPanel } from "@/features/logins/LoginsPage";
import { StateBoardPanel } from "@/features/team/StateBoardPanel";
import { useEmployees, useTeamMutations } from "@/features/team/useTeam";
import type { Employee } from "@/types/employee";

export function TeamPage() {
  const [page, setPage] = useState(1);
  const [q, setQ] = useState("");
  const [editing, setEditing] = useState<Employee | null | undefined>(undefined);
  const [partnerEditing, setPartnerEditing] = useState<Employee | null | undefined>(undefined);
  const [adminEditing, setAdminEditing] = useState<Employee | null | undefined>(undefined);
  const [importing, setImporting] = useState(false);
  const { hasRole } = useAuth();
  const isFullAdmin = hasRole("admin"); // only a full admin can create admins or change admin access
  const [resetting, setResetting] = useState<Employee | null>(null);
  const canReset = usePermission("employees.update");

  const canCreate = usePermission("employees.create");
  const canAssign = usePermission("assignments.manage");
  const canDeactivate = usePermission("employees.deactivate");
  const canLogins = usePermission("logins.view");
  const [view, setView] = useState<"team" | "logins">("team");
  const { deactivate } = useTeamMutations();
  const [category, setCategory] = useState("");
  const { data, isLoading, isError, refetch } = useEmployees(page, q, category);

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Users & access"
        subtitle="Admins, staff and Blinkit / Zepto partner logins — their scope, and what each person can see."
        action={
          canCreate && view === "team" && (
            <div className="flex flex-wrap gap-2">
              <Button variant="secondary" onClick={() => setImporting(true)}>
                <IconUpload className="h-4 w-4" /> Import employees
              </Button>
              {isFullAdmin && (
                <Button variant="secondary" onClick={() => setAdminEditing(null)}>
                  <IconPlus className="h-4 w-4" /> New admin
                </Button>
              )}
              <Button variant="secondary" onClick={() => setPartnerEditing(null)}>
                <IconPlus className="h-4 w-4" /> Partner account
              </Button>
              <Button onClick={() => setEditing(null)}>
                <IconPlus className="h-4 w-4" /> New employee
              </Button>
            </div>
          )
        }
      />

      <div role="tablist" aria-label="Staff category" className="flex flex-wrap gap-1.5">
        {[
          ["", "All staff"],
          ["admin", "Admins"],
          ["accounts", "Accounts"],
          ["partner", "Partner accounts"],
          ["blinkit", "Blinkit employees"],
          ["zepto", "Zepto employees"],
        ].map(([id, label]) => (
          <button
            key={id}
            role="tab"
            aria-selected={view === "team" && category === id}
            onClick={() => {
              setView("team");
              setCategory(id);
              setPage(1);
            }}
            className={`rounded-lg px-3.5 py-2 text-sm font-semibold transition-colors ${
              view === "team" && category === id ? "bg-brand-500 text-white shadow-sm" : "bg-surface text-gray-600 ring-1 ring-surface-border hover:bg-surface-subtle"
            }`}
          >
            {label}
          </button>
        ))}
        {canLogins && (
          <button
            role="tab"
            aria-selected={view === "logins"}
            onClick={() => setView("logins")}
            className={`rounded-lg px-3.5 py-2 text-sm font-semibold transition-colors ${
              view === "logins" ? "bg-brand-500 text-white shadow-sm" : "bg-surface text-gray-600 ring-1 ring-surface-border hover:bg-surface-subtle"
            }`}
          >
            Vendor &amp; POC logins
          </button>
        )}
      </div>

      {view === "logins" && <LoginsPanel />}
      {view === "team" && (<>
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
                <Th>Login ID</Th>
                <Th>Name</Th>
                <Th>Category</Th>
                <Th>Platform</Th>
                <Th>Scope</Th>
                <Th>Permissions</Th>
                <Th>Status</Th>
                {(canCreate || canDeactivate || canReset) && <Th className="text-right">Actions</Th>}
              </tr>
            </thead>
            <tbody>
              {data.items.length === 0 && <TableEmpty colSpan={8}>No one in this category yet.</TableEmpty>}
              {data.items.map((e) => (
                <tr key={e.id}>
                  <Td className="font-medium text-gray-900">{e.employeeCode}</Td>
                  <Td>{e.fullName}</Td>
                  <Td>
                    <Badge tone={e.category === "admin" ? "danger" : e.category === "accounts" ? "warning" : e.category === "partner" ? "success" : "info"}>
                      {e.category === "admin" ? (e.adminLevel === "custom" ? "Custom admin" : "Admin") : e.categoryLabel || e.category}
                    </Badge>
                  </Td>
                  <Td>{e.platformSlug ?? "—"}</Td>
                  <Td>{e.category === "partner" ? "All stores on platform" : e.category === "admin" ? "Whole company" : (e.regions.length ? (
                    <span>
                      {e.regions.map((r) => r.name).join(", ")}
                      {(e.includedStates.length > 0 || e.includedCities.length > 0) && (
                        <span className="block text-xs text-status-success">plus {[...e.includedStates, ...e.includedCities].join(", ")}</span>
                      )}
                      {(e.excludedStates.length > 0 || e.excludedCities.length > 0) && (
                        <span className="block text-xs text-status-danger">except {[...e.excludedStates, ...e.excludedCities].join(", ")}</span>
                      )}
                    </span>
                  ) : e.includedStates.length > 0 || e.includedCities.length > 0 ? (
                    <span className="text-status-success">{[...e.includedStates, ...e.includedCities].join(", ")}</span>
                  ) : (e.states.length ? e.states.join(", ") : "—"))}</Td>
                  <Td>{e.adminLevel === "full" ? "Full access" : e.directPermissions.length}</Td>
                  <Td>
                    <Badge tone={e.isActive ? "success" : "neutral"}>{e.isActive ? "Active" : "Deactivated"}</Badge>
                  </Td>
                  {(canCreate || canDeactivate || canReset) && (
                    <Td className="text-right">
                      {e.category === "admin" && !isFullAdmin ? (
                        <span className="text-xs text-gray-400">Managed by admins</span>
                      ) : (
                      <div className="flex items-center justify-end gap-3 whitespace-nowrap text-sm font-medium">
                        {canCreate && (
                          <button className="text-brand-600 hover:text-brand-700" onClick={() => (e.category === "partner" ? setPartnerEditing(e) : e.category === "admin" ? setAdminEditing(e) : setEditing(e))}>
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
                      )}
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
      </>)}

      {editing !== undefined && (
        <EmployeeAccessModal key={editing?.id ?? "new"} onClose={() => setEditing(undefined)} employee={editing ?? null} />
      )}
      {partnerEditing !== undefined && (
        <PartnerAccountModal key={partnerEditing?.id ?? "new"} onClose={() => setPartnerEditing(undefined)} account={partnerEditing ?? null} />
      )}
      {adminEditing !== undefined && (
        <AdminAccountModal key={adminEditing?.id ?? "new"} onClose={() => setAdminEditing(undefined)} account={adminEditing ?? null} />
      )}
      {importing && <ImportEmployeesModal onClose={() => setImporting(false)} />}
      {resetting && <ResetPasswordModal employee={resetting} onClose={() => setResetting(null)} />}
    </div>
  );
}
