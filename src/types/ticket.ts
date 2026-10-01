export type TicketStatus = "OPEN" | "IN_PROGRESS" | "RESOLVED" | "CLOSED";
export type TicketPriority = "LOW" | "MEDIUM" | "HIGH" | "URGENT";
export type TicketCategory = "LATE_DELIVERY" | "NO_DELIVERY" | "SHORT_SUPPLY" | "QUALITY" | "DAMAGED" | "BILLING" | "OTHER";

export interface StoreBrief {
  id: string;
  name: string;
  code: string;
  city: string | null;
  state: string | null;
  regionId: string | null;
  regionName: string | null;
  vendorName: string | null;
  vendorNumber: string | null;
  platformSlug: string | null;
  platformName: string | null;
}

export interface Ticket {
  id: string;
  number: number;
  store: StoreBrief;
  category: TicketCategory;
  priority: TicketPriority;
  status: TicketStatus;
  title: string;
  description: string | null;
  createdByName: string | null;
  assignedToId: string | null;
  assignedToName: string | null;
  createdAt: string;
  updatedAt: string;
  dueAt: string | null;
  resolvedAt: string | null;
  isOverdue: boolean;
  commentsCount: number;
  nextStatuses: TicketStatus[];
  canAssign: boolean;
  canSetPriority: boolean;
}

export interface TicketComment {
  id: string;
  authorName: string | null;
  body: string;
  event: string | null;
  createdAt: string;
}

export interface TicketDetail extends Ticket {
  comments: TicketComment[];
  assignees: { id: string; name: string; code: string }[];
}

export interface TicketInput {
  storeId: string;
  category: TicketCategory;
  priority: TicketPriority;
  title: string;
  description?: string;
}

export interface TicketFilters {
  status: "active" | "done" | "";
  category: string;
  priority: string;
  partner: string;
  regionId: string;
  q: string;
  overdue: boolean;
  mine: boolean;
}

export interface Bucket {
  label: string;
  total: number;
  active: number;
  delivery: number;
  overdue: number;
  severity: "ok" | "medium" | "high";
}

export interface Hotspot {
  storeId: string;
  name: string;
  code: string;
  state: string | null;
  regionName: string | null;
  vendorName: string | null;
  platformName: string | null;
  active: number;
  delivery: number;
  overdue: number;
  total: number;
}

export interface TicketAnalytics {
  days: number;
  summary: {
    open: number;
    inProgress: number;
    overdue: number;
    deliveryActive: number;
    raised: number;
    resolved: number;
    avgResolutionHours: number | null;
  };
  byRegion: Bucket[];
  byState: Bucket[];
  byVendor: Bucket[];
  byPlatform: Bucket[];
  byCategory: { category: TicketCategory; count: number }[];
  trend: { label: string; created: number; resolved: number }[];
  hotspots: Hotspot[];
}

export const CATEGORY_LABEL: Record<TicketCategory, string> = {
  LATE_DELIVERY: "Late delivery",
  NO_DELIVERY: "No delivery",
  SHORT_SUPPLY: "Short supply",
  QUALITY: "Water quality",
  DAMAGED: "Damaged bottles",
  BILLING: "Billing",
  OTHER: "Other",
};

export const PRIORITY_LABEL: Record<TicketPriority, string> = { LOW: "Low", MEDIUM: "Medium", HIGH: "High", URGENT: "Urgent" };

export const STATUS_LABEL: Record<TicketStatus, string> = {
  OPEN: "Open",
  IN_PROGRESS: "In progress",
  RESOLVED: "Resolved",
  CLOSED: "Closed",
};

/** What a person does to move a ticket to this status (button text). */
export const STATUS_ACTION: Record<TicketStatus, string> = {
  OPEN: "Reopen",
  IN_PROGRESS: "Start work",
  RESOLVED: "Mark resolved",
  CLOSED: "Confirm & close",
};

export const TICKET_CODE = (n: number) => `TK-${String(n).padStart(4, "0")}`;
