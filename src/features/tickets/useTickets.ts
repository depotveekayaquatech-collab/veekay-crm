import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { addComment, createTicket, getTicket, getTicketAnalytics, listTickets, searchStores, updateTicket } from "@/services/tickets";
import { pushToast } from "@/lib/toast";
import type { TicketFilters, TicketInput, TicketPriority, TicketStatus } from "@/types/ticket";

export function useTickets(filters: TicketFilters, page: number) {
  return useQuery({
    queryKey: ["tickets", filters, page],
    queryFn: () => listTickets(filters, page),
    placeholderData: keepPreviousData,
  });
}

export function useTicket(id: string | null) {
  return useQuery({ queryKey: ["ticket", id], queryFn: () => getTicket(id as string), enabled: Boolean(id) });
}

export function useTicketAnalytics(days: number, enabled: boolean) {
  return useQuery({ queryKey: ["ticket-analytics", days], queryFn: () => getTicketAnalytics(days), enabled, staleTime: 30_000 });
}

export function useStoreSearch(q: string) {
  return useQuery({ queryKey: ["ticket-stores", q], queryFn: () => searchStores(q), staleTime: 60_000, placeholderData: keepPreviousData });
}

export function useTicketMutations() {
  const qc = useQueryClient();
  const refresh = (id?: string) => {
    qc.invalidateQueries({ queryKey: ["tickets"] });
    qc.invalidateQueries({ queryKey: ["ticket-analytics"] });
    if (id) qc.invalidateQueries({ queryKey: ["ticket", id] });
  };
  return {
    create: useMutation({
      mutationFn: (input: TicketInput) => createTicket(input),
      onSuccess: () => {
        refresh();
        pushToast("Ticket raised.", "success");
      },
    }),
    update: useMutation({
      mutationFn: ({ id, ...change }: { id: string; status?: TicketStatus; priority?: TicketPriority; assignedToId?: string; unassign?: boolean }) =>
        updateTicket(id, change),
      onSuccess: (t) => {
        qc.setQueryData(["ticket", t.id], t);
        refresh();
      },
    }),
    comment: useMutation({
      mutationFn: ({ id, body }: { id: string; body: string }) => addComment(id, body),
      onSuccess: (t) => {
        qc.setQueryData(["ticket", t.id], t);
        qc.invalidateQueries({ queryKey: ["tickets"] });
      },
    }),
  };
}
