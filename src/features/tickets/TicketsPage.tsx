import { useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { PageHeader } from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Pagination } from "@/components/ui/Pagination";
import { Select } from "@/components/ui/Select";
import { Skeleton } from "@/components/feedback/Skeleton";
import { ErrorState } from "@/components/feedback/ErrorState";
import { EmptyState } from "@/components/feedback/EmptyState";
import { IconPlus } from "@/components/ui/icons";
import { RegionFilter, SearchBox, SegmentedControl } from "@/features/orders/ui";
import { CategoryBadge, PriorityBadge, StatusBadge } from "@/features/tickets/parts";
import { dueLabel, timeAgo } from "@/lib/ticketTime";
import { NewTicketModal } from "@/features/tickets/NewTicketModal";
import { TicketDetailModal } from "@/features/tickets/TicketDetailModal";
import { TicketInsights } from "@/features/tickets/TicketInsights";
import { useTickets } from "@/features/tickets/useTickets";
import { useAllStores } from "@/features/stores/useAllStores";
import { usePartners } from "@/features/stores/useStores";
import { usePermission } from "@/hooks/usePermission";
import { useAuth } from "@/features/auth/useAuth";
import { distinctOptions } from "@/lib/options";
import { CATEGORY_LABEL, PRIORITY_LABEL, TICKET_CODE, type TicketFilters } from "@/types/ticket";

const EMPTY: TicketFilters = { status: "active", category: "", priority: "", partner: "", regionId: "", q: "", overdue: false, mine: false };
const CATEGORIES = Object.entries(CATEGORY_LABEL).map(([value, label]) => ({ value, label }));
const PRIORITIES = Object.entries(PRIORITY_LABEL).map(([value, label]) => ({ value, label }));

function List({ isAdmin }: { isAdmin: boolean }) {
  const [filters, setFilters] = useState<TicketFilters>(EMPTY);
  const [page, setPage] = useState(1);
  const [openId, setOpenId] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const canCreate = usePermission("tickets.create") || isAdmin;
  const { data, isLoading, isError, refetch, isFetching } = useTickets(filters, page);

  // Platform + region filters are for admins, who see every region; the region list follows the platform.
  const { data: partners = [] } = usePartners(isAdmin);
  const { data: stores = [] } = useAllStores(isAdmin);
  const regions = useMemo(
    () =>
      distinctOptions(
        stores.filter((s) => !filters.partner || s.partnerSlug === filters.partner),
        (s) => (s.regionId ? { value: s.regionId, label: s.regionName ?? "Region" } : null),
      ),
    [stores, filters.partner],
  );

  function set(patch: Partial<TicketFilters>) {
    setFilters((f) => ({ ...f, ...patch }));
    setPage(1);
  }

  const filtered = filters.category || filters.priority || filters.partner || filters.regionId || filters.q || filters.overdue || filters.mine;

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-end gap-3">
        <SegmentedControl
          label="Status"
          value={filters.status}
          onChange={(v) => set({ status: v })}
          options={[
            { value: "active", label: "Active" },
            { value: "done", label: "Resolved" },
            { value: "", label: "All" },
          ]}
        />
        {isAdmin && partners.length > 0 && (
          <SegmentedControl
            label="Platform"
            value={filters.partner}
            onChange={(v) => set({ partner: v, regionId: "" })}
            options={[{ value: "", label: "All platforms" }, ...partners.map((p) => ({ value: p.slug, label: p.name }))]}
          />
        )}
        {isAdmin && regions.length > 1 && <RegionFilter value={filters.regionId} onChange={(v) => set({ regionId: v })} options={regions} className="sm:w-48 [&_label]:sr-only" />}
        <div className="w-full sm:w-44 [&_label]:sr-only">
          <Select label="Category" value={filters.category} onChange={(e) => set({ category: e.target.value })} placeholder="All categories" options={CATEGORIES} />
        </div>
        <div className="w-full sm:w-40 [&_label]:sr-only">
          <Select label="Priority" value={filters.priority} onChange={(e) => set({ priority: e.target.value })} placeholder="All priorities" options={PRIORITIES} />
        </div>
        <SearchBox value={filters.q} onChange={(v) => set({ q: v })} placeholder="Search ticket, store, city or vendor" className="w-full sm:ml-auto sm:w-72" />
      </div>

      <div className="flex flex-wrap items-center gap-4 text-sm text-gray-600">
        <label className="flex cursor-pointer items-center gap-2">
          <input type="checkbox" checked={filters.overdue} onChange={(e) => set({ overdue: e.target.checked })} className="accent-brand-500" />
          Overdue only
        </label>
        <label className="flex cursor-pointer items-center gap-2">
          <input type="checkbox" checked={filters.mine} onChange={(e) => set({ mine: e.target.checked })} className="accent-brand-500" />
          Raised by or assigned to me
        </label>
        {filtered && (
          <button className="text-sm font-semibold text-brand-600 hover:text-brand-700" onClick={() => set({ ...EMPTY, status: filters.status })}>
            Clear filters
          </button>
        )}
        <span className="ml-auto text-xs text-gray-400">{isFetching ? "Updating…" : data ? `${data.total} ticket${data.total === 1 ? "" : "s"}` : ""}</span>
        {canCreate && (
          <Button onClick={() => setCreating(true)}>
            <IconPlus className="h-4 w-4" /> Raise ticket
          </Button>
        )}
      </div>

      {isLoading && <Skeleton className="h-72" />}
      {isError && <ErrorState message="Couldn't load tickets." onRetry={() => refetch()} />}
      {data && data.items.length === 0 && (
        <EmptyState
          title={filtered || filters.status !== "active" ? "No tickets match" : "No active tickets"}
          description={filtered ? "Try clearing a filter." : "Nothing needs attention right now."}
        />
      )}

      {data && data.items.length > 0 && (
        <>
          <div className="stacked-table overflow-x-auto rounded-xl border border-surface-border bg-surface shadow-card">
            <table className="w-full min-w-[820px] text-sm">
              <thead>
                <tr className="border-b border-surface-border bg-surface-subtle text-left text-xs font-semibold uppercase tracking-wide text-gray-500">
                  <th className="px-5 py-3">Ticket</th>
                  <th className="px-4 py-3">Store</th>
                  <th className="px-4 py-3">Issue</th>
                  <th className="px-4 py-3">Status</th>
                  <th className="px-4 py-3">Age / deadline</th>
                  <th className="px-4 py-3">Assigned</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((t) => {
                  const due = t.status === "OPEN" || t.status === "IN_PROGRESS" ? dueLabel(t.dueAt) : null;
                  return (
                    <tr
                      key={t.id}
                      onClick={() => setOpenId(t.id)}
                      className={`cursor-pointer border-b border-surface-border transition-colors last:border-0 hover:bg-surface-subtle ${t.isOverdue ? "bg-status-danger-soft/30" : ""}`}
                    >
                      <td className="px-5 py-3" data-label="Ticket">
                        <div className="flex items-center gap-1.5 text-xs font-semibold text-gray-400">{TICKET_CODE(t.number)}{t.source === "google" && <Badge tone="info">Google</Badge>}</div>
                        <div className="max-w-[18rem] truncate font-medium text-gray-900">{t.title}</div>
                        {t.commentsCount > 0 && <div className="text-xs text-gray-400">{t.commentsCount} comment{t.commentsCount === 1 ? "" : "s"}</div>}
                      </td>
                      <td className="px-4 py-3" data-label="Store">
                        <div className="font-medium text-gray-900">{t.store.name}</div>
                        <div className="text-xs text-gray-500">{[t.store.regionName, t.store.state, t.store.platformName].filter(Boolean).join(" · ")}</div>
                      </td>
                      <td className="px-4 py-3" data-label="Issue">
                        <div className="flex flex-wrap gap-1.5">
                          <CategoryBadge category={t.category} />
                          <PriorityBadge priority={t.priority} />
                        </div>
                      </td>
                      <td className="px-4 py-3" data-label="Status">
                        <div className="flex flex-wrap items-center gap-1.5">
                          <StatusBadge status={t.status} />
                          {t.isOverdue && <Badge tone="danger">Overdue</Badge>}
                        </div>
                      </td>
                      <td className="px-4 py-3" data-label="Age / deadline">
                        <div className="text-gray-700">{timeAgo(t.createdAt)}</div>
                        {due && <div className={`text-xs ${due.late ? "font-semibold text-status-danger" : "text-gray-500"}`}>{due.text}</div>}
                      </td>
                      <td className="px-4 py-3 text-gray-700" data-label="Assigned">{t.assignedToName ?? <span className="text-gray-400">—</span>}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <Pagination page={data.page} pageSize={data.pageSize} total={data.total} onPageChange={setPage} />
        </>
      )}

      {openId && <TicketDetailModal id={openId} onClose={() => setOpenId(null)} />}
      {creating && (
        <NewTicketModal
          onClose={() => setCreating(false)}
          onCreated={(id) => {
            setCreating(false);
            setOpenId(id);
          }}
        />
      )}
    </div>
  );
}

export function TicketsPage() {
  const { user } = useAuth();
  const isAdmin = usePermission("tickets.manage");
  const [params, setParams] = useSearchParams();
  const tab = isAdmin && params.get("tab") === "insights" ? "insights" : "list";
  const isPartner = Boolean(user?.roles.includes("partner"));

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Tickets"
        subtitle={
          isAdmin
            ? "Every issue raised against a store, across all regions — and where problems are building up."
            : isPartner
              ? "Raise an issue with a store's delivery and follow it until it's fixed."
              : "Issues raised for the stores in your region. Pick one up, update it, and mark it resolved."
        }
      />
      {isAdmin && (
        <SegmentedControl
          label="Tickets view"
          value={tab}
          onChange={(v) => setParams(v === "insights" ? { tab: "insights" } : {}, { replace: true })}
          options={[
            { value: "list", label: "All tickets" },
            { value: "insights", label: "Insights" },
          ]}
        />
      )}
      {tab === "insights" ? <TicketInsights /> : <List isAdmin={isAdmin} />}
    </div>
  );
}
