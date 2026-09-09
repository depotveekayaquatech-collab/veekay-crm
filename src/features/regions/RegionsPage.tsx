import { useState } from "react";
import { PageHeader } from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Pagination } from "@/components/ui/Pagination";
import { Table, Td, Th, TableEmpty } from "@/components/ui/Table";
import { Skeleton } from "@/components/feedback/Skeleton";
import { ErrorState } from "@/components/feedback/ErrorState";
import { IconPlus } from "@/components/ui/icons";
import { usePermission } from "@/hooks/usePermission";
import { RegionFormModal } from "@/features/regions/RegionFormModal";
import { useRegions } from "@/features/regions/useRegions";
import type { Region } from "@/types/region";

export function RegionsPage() {
  const [page, setPage] = useState(1);
  const [editing, setEditing] = useState<Region | null | undefined>(undefined);
  const canManage = usePermission("regions.manage");
  const { data, isLoading, isError, refetch } = useRegions(page);

  const modalOpen = editing !== undefined;

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Regions"
        subtitle="Operational areas your field teams and stores are grouped into."
        action={
          canManage && (
            <Button onClick={() => setEditing(null)}>
              <IconPlus className="h-4 w-4" />
              New region
            </Button>
          )
        }
      />

      {isLoading && <Skeleton className="h-64" />}
      {isError && <ErrorState message="Couldn't load regions." onRetry={() => refetch()} />}

      {data && (
        <>
          <Table>
            <thead>
              <tr>
                <Th>Name</Th>
                <Th>Code</Th>
                <Th>Stores</Th>
                <Th>Status</Th>
                {canManage && <Th className="w-24 text-right">Actions</Th>}
              </tr>
            </thead>
            <tbody>
              {data.items.length === 0 && (
                <TableEmpty colSpan={canManage ? 5 : 4}>No regions yet.</TableEmpty>
              )}
              {data.items.map((region) => (
                <tr key={region.id}>
                  <Td className="font-medium text-gray-900">{region.name}</Td>
                  <Td>{region.code}</Td>
                  <Td>{region.storeCount}</Td>
                  <Td>
                    <Badge tone={region.isActive ? "success" : "neutral"}>
                      {region.isActive ? "Active" : "Inactive"}
                    </Badge>
                  </Td>
                  {canManage && (
                    <Td className="text-right">
                      <button
                        className="text-sm font-medium text-brand-600 hover:text-brand-700"
                        onClick={() => setEditing(region)}
                      >
                        Edit
                      </button>
                    </Td>
                  )}
                </tr>
              ))}
            </tbody>
          </Table>
          <Pagination
            page={data.page}
            pageSize={data.pageSize}
            total={data.total}
            onPageChange={setPage}
          />
        </>
      )}

      {modalOpen && (
        <RegionFormModal
          key={editing?.id ?? "new"}
          onClose={() => setEditing(undefined)}
          region={editing ?? null}
        />
      )}
    </div>
  );
}
