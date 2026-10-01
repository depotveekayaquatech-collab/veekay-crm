import { apiRequest } from "@/services/api";
import { camelize } from "@/lib/camel";
import type { Page, PageWire } from "@/types/common";
import type {
  StoreBrief,
  Ticket,
  TicketAnalytics,
  TicketDetail,
  TicketFilters,
  TicketInput,
  TicketStatus,
  TicketPriority,
} from "@/types/ticket";

export async function listTickets(filters: TicketFilters, page: number): Promise<Page<Ticket>> {
  const qs = new URLSearchParams({ page: String(page), page_size: "25" });
  if (filters.status) qs.set("status", filters.status);
  if (filters.category) qs.set("category", filters.category);
  if (filters.priority) qs.set("priority", filters.priority);
  if (filters.partner) qs.set("partner", filters.partner);
  if (filters.regionId) qs.set("region_id", filters.regionId);
  if (filters.q.trim()) qs.set("q", filters.q.trim());
  if (filters.overdue) qs.set("overdue", "true");
  if (filters.mine) qs.set("mine", "true");
  const wire = await apiRequest<PageWire<unknown>>(`/tickets?${qs}`);
  return camelize<Page<Ticket>>(wire);
}

export async function getTicket(id: string): Promise<TicketDetail> {
  return camelize<TicketDetail>(await apiRequest(`/tickets/${id}`));
}

export async function createTicket(input: TicketInput): Promise<TicketDetail> {
  const body = {
    store_id: input.storeId,
    category: input.category,
    priority: input.priority,
    title: input.title,
    description: input.description || null,
  };
  return camelize<TicketDetail>(await apiRequest("/tickets", { method: "POST", body }));
}

export async function updateTicket(
  id: string,
  change: { status?: TicketStatus; priority?: TicketPriority; assignedToId?: string; unassign?: boolean },
): Promise<TicketDetail> {
  const body = { status: change.status, priority: change.priority, assigned_to_id: change.assignedToId, unassign: change.unassign };
  return camelize<TicketDetail>(await apiRequest(`/tickets/${id}`, { method: "PATCH", body }));
}

export async function addComment(id: string, body: string): Promise<TicketDetail> {
  return camelize<TicketDetail>(await apiRequest(`/tickets/${id}/comments`, { method: "POST", body: { body } }));
}

export async function searchStores(q: string): Promise<StoreBrief[]> {
  return camelize<StoreBrief[]>(await apiRequest(`/tickets/stores?q=${encodeURIComponent(q)}`));
}

export async function getTicketAnalytics(days: number): Promise<TicketAnalytics> {
  return camelize<TicketAnalytics>(await apiRequest(`/tickets/analytics?days=${days}`));
}
