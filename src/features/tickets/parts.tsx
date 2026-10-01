import { Badge } from "@/components/ui/Badge";
import {
  CATEGORY_LABEL,
  PRIORITY_LABEL,
  STATUS_LABEL,
  type TicketCategory,
  type TicketPriority,
  type TicketStatus,
} from "@/types/ticket";

export function StatusBadge({ status }: { status: TicketStatus }) {
  const tone = status === "OPEN" ? "warning" : status === "IN_PROGRESS" ? "info" : status === "RESOLVED" ? "success" : "neutral";
  return <Badge tone={tone}>{STATUS_LABEL[status]}</Badge>;
}

export function PriorityBadge({ priority }: { priority: TicketPriority }) {
  const tone = priority === "URGENT" ? "danger" : priority === "HIGH" ? "warning" : priority === "MEDIUM" ? "info" : "neutral";
  return <Badge tone={tone}>{PRIORITY_LABEL[priority]}</Badge>;
}

export function CategoryBadge({ category }: { category: TicketCategory }) {
  const delivery = category === "LATE_DELIVERY" || category === "NO_DELIVERY";
  return <Badge tone={delivery ? "danger" : "neutral"}>{CATEGORY_LABEL[category]}</Badge>;
}
