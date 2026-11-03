import { useState } from "react";
import { EmptyState } from "@/components/feedback/EmptyState";
import { ErrorState } from "@/components/feedback/ErrorState";
import { Skeleton } from "@/components/feedback/Skeleton";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Pagination } from "@/components/ui/Pagination";
import { Table, Td, Th } from "@/components/ui/Table";
import { ADMIN_PAGE_SIZE, EMPTY_VENDOR, formToPatch, useAdminVendors, useVendorMutations, type AdminVendor, type VendorForm } from "@/features/vendorpay/adminApi";
import { Amount } from "@/features/vendorpay/parts";
import { VendorFormModal } from "@/features/vendorpay/VendorFormModal";
import { useDebounced } from "@/hooks/useDebounced";

const toForm = (v: AdminVendor): VendorForm => ({
  vendorCode: v.vendorCode, name: v.name, city: v.city ?? "", openingBalance: Number(v.openingBalance) ? v.openingBalance : "", openingDate: v.openingDate ?? "",
});

export function AdminVendorsTab() {
  const [search, setSearch] = useState("");
  const q = useDebounced(search.trim());
  const [page, setPage] = useState(1);
  const [editing, setEditing] = useState<AdminVendor | "new" | null>(null);
  const { data, isLoading, isError, refetch } = useAdminVendors(q, page);
  const { create, update } = useVendorMutations();

  async function save(form: VendorForm) {
    try {
      if (editing === "new") await create.mutateAsync(form);
      else if (editing) await update.mutateAsync({ code: editing.vendorCode, patch: formToPatch(form) });
      setEditing(null);
    } catch {
      /* the API layer already showed the reason (for example a duplicate code) */
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="w-full sm:max-w-xs">
          <Input label="Search vendors" value={search} placeholder="Name, city or code" onChange={(e) => { setSearch(e.target.value); setPage(1); }} />
        </div>
        <Button onClick={() => setEditing("new")}>Add vendor</Button>
      </div>

      {isError ? (
        <ErrorState message="Couldn't load the vendors." onRetry={() => void refetch()} />
      ) : isLoading || !data ? (
        <Skeleton className="h-64 w-full" />
      ) : data.total === 0 ? (
        <EmptyState title={q ? "No vendor matches that search" : "No vendors yet"} description={q ? undefined : "Add a vendor, or approve the codes that arrive from Busy on the Unmatched codes tab."} />
      ) : (
        <>
          <Table>
            <thead>
              <tr>
                <Th>Code</Th>
                <Th>Name</Th>
                <Th>City</Th>
                <Th className="text-right">Opening balance</Th>
                <Th>Status</Th>
                <Th className="text-right">Actions</Th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((v) => (
                <tr key={v.id}>
                  <Td className="tabular-nums font-semibold text-heading">{v.vendorCode}</Td>
                  <Td>{v.name}</Td>
                  <Td>{v.city ?? ""}</Td>
                  <Td className="text-right">
                    <Amount value={v.openingBalance} />
                    {v.openingDate && <span className="block text-[11px] text-gray-500">as of {v.openingDate}</span>}
                  </Td>
                  <Td><Badge tone={v.isActive ? "success" : "neutral"}>{v.isActive ? "Active" : "Hidden"}</Badge></Td>
                  <Td className="text-right">
                    <div className="flex justify-end gap-2">
                      <Button size="sm" variant="secondary" onClick={() => setEditing(v)}>Edit</Button>
                      <Button size="sm" variant="ghost" disabled={update.isPending} onClick={() => update.mutate({ code: v.vendorCode, patch: { is_active: !v.isActive } })}>
                        {v.isActive ? "Hide" : "Show"}
                      </Button>
                    </div>
                  </Td>
                </tr>
              ))}
            </tbody>
          </Table>
          <Pagination page={page} pageSize={ADMIN_PAGE_SIZE} total={data.total} onPageChange={setPage} />
        </>
      )}

      {editing && (
        <VendorFormModal
          key={editing === "new" ? "new" : editing.vendorCode}
          title={editing === "new" ? "Add vendor" : `Edit ${editing.vendorCode}`}
          description={editing === "new" ? undefined : "Hidden vendors stop showing for employees but keep their entries, and Busy can still send for them."}
          initial={editing === "new" ? EMPTY_VENDOR : toForm(editing)}
          codeLocked={editing !== "new"}
          isSaving={create.isPending || update.isPending}
          onClose={() => setEditing(null)}
          onSubmit={(form) => void save(form)}
        />
      )}
    </div>
  );
}
