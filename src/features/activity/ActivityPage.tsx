import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { PageHeader } from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/Badge";
import { Pagination } from "@/components/ui/Pagination";
import { Select } from "@/components/ui/Select";
import { Skeleton } from "@/components/feedback/Skeleton";
import { EmptyState } from "@/components/feedback/EmptyState";
import { listActivity } from "@/services/activity";
import type { Activity } from "@/types/activity";

const ENTITY_OPTIONS = [
  { value: "order_entry", label: "Order entries" },
  { value: "store", label: "Stores" },
  { value: "region", label: "Regions" },
  { value: "employee", label: "Employees" },
  { value: "state_assignment", label: "State assignments" },
];

function describe(a: Activity): string {
  const verb = (a.action.split(".")[1] ?? a.action).replace(/_/g, " ");
  const m = a.metadata ?? {};
  const label =
    (m.store_name as string) || (m.full_name as string) || (m.name as string) ||
    (m.state as string) || (m.employee_code as string) || a.entityId.slice(0, 8);
  const extra = m.order_date ? ` (${m.order_date}${m.bottle_count != null ? `, ${m.bottle_count}` : ""})` : "";
  return `${a.entityType.replace(/_/g, " ")} ${verb} — ${label}${extra}`;
}

function ago(iso: string): string {
  const mins = Math.round((Date.now() - new Date(iso).getTime()) / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.round(mins / 60);
  return hrs < 24 ? `${hrs}h ago` : new Date(iso).toLocaleDateString();
}

export function ActivityPage() {
  const [page, setPage] = useState(1);
  const [entityType, setEntityType] = useState("");
  const { data, isLoading } = useQuery({
    queryKey: ["activity", page, entityType],
    queryFn: () => listActivity({ page, pageSize: 25, entityType: entityType || undefined }),
  });

  return (
    <div className="flex flex-col gap-6">
      <PageHeader title="Audit log" subtitle="Every change in the workspace, newest first." />
      <Select
        label="Filter"
        value={entityType}
        onChange={(e) => { setEntityType(e.target.value); setPage(1); }}
        placeholder="All activity"
        options={ENTITY_OPTIONS}
        className="sm:max-w-xs"
      />

      {isLoading && <Skeleton className="h-64" />}
      {data && data.items.length === 0 && <EmptyState title="Nothing here yet" />}
      {data && data.items.length > 0 && (
        <>
          <div className="divide-y divide-surface-border rounded-lg border border-surface-border bg-white shadow-card">
            {data.items.map((a) => (
              <div key={a.id} className="flex items-start justify-between gap-4 px-4 py-3">
                <div className="min-w-0">
                  <p className="text-sm text-gray-900">{describe(a)}</p>
                  <p className="mt-0.5 text-xs text-gray-500">{a.actorName ?? "System"} · {ago(a.createdAt)}</p>
                </div>
                <Badge tone="neutral">{a.action.split(".")[1]?.replace(/_/g, " ") ?? a.action}</Badge>
              </div>
            ))}
          </div>
          <Pagination page={data.page} pageSize={data.pageSize} total={data.total} onPageChange={setPage} />
        </>
      )}
    </div>
  );
}
