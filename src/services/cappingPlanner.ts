import { camelize } from "@/lib/camel";
import { apiBlob, apiRequest } from "@/services/api";

export type PlannerMode = "max_capacity" | "priority_first";
export type PlannerProject = "zepto" | "blinkit" | "all";

/** What to calculate. A null storeLimit means every eligible store. */
export interface PlanRequest {
  month: string;
  project: PlannerProject;
  mode: PlannerMode;
  storeLimit: number | null;
  target: number;
  priority: string[];
}

export interface PlanRow {
  storeId: string;
  crmCode: string;
  outletId: string;
  name: string;
  project: string;
  state: string | null;
  city: string | null;
  dailyCap: number | null;
  monthlyLimit: number | null;
  /** Recorded for the month (actual). */
  used: number;
  entries: number;
  /** Limit minus recorded, never below 0. */
  remaining: number;
  overBy: number;
  /** Why the store is not verified; null when it is. */
  excludeReason: string | null;
  selected: boolean;
  selectionRank: number | null;
  priorityRank: number | null;
  /** Capacity that counts: remaining for a verified store, else 0. */
  capacity: number;
  /** The plan's proposal for this store (not supply). */
  proposed: number;
  /** Recorded + proposed. */
  finalPlanned: number;
}

export type PriorityStatus = "matched" | "unmatched" | "ambiguous" | "duplicate" | "other_project";

export interface PriorityEntry {
  position: number;
  raw: string;
  status: PriorityStatus;
  message: string;
  storeId: string | null;
  crmCode: string | null;
  outletId: string | null;
  name: string | null;
  project: string | null;
  candidates: { crmCode: string; outletId: string; name: string; project: string }[];
  outcome: string;
  included: boolean;
}

export interface PlanIssue {
  code: string;
  severity: "error" | "warning" | "info";
  storeId: string;
  crmCode: string;
  outletId: string;
  name: string;
  project: string;
  message: string;
}

export interface PlanTotals {
  stores: number;
  eligible: number;
  excluded: number;
  selected: number;
  storeLimit: number | null;
  currentTotal: number;
  desiredTotal: number;
  target: number;
  availableCapacity: number;
  selectedCapacity: number;
  matchable: number;
  unmatched: number;
  unusedCapacity: number;
  percentCovered: number | null;
  /** How many stores, in the same order, the target needs; null when it fits or nothing can cover it. */
  storesRequired: number | null;
  coverable: boolean;
  fits: boolean;
  allocationAllowed: boolean;
  proposedTotal: number;
  priorityTotal: number;
  priorityMatched: number;
  priorityIncluded: number;
  priorityExceedsLimit: boolean;
}

export interface PlanResult {
  month: string;
  monthLabel: string;
  project: PlannerProject;
  mode: PlannerMode;
  note: string;
  allocationNote: string | null;
  totals: PlanTotals;
  rows: PlanRow[];
  priority: PriorityEntry[];
  issues: PlanIssue[];
}

/** Calculate. Read-only: nothing is saved and no entry changes. */
export async function runPlan(req: PlanRequest): Promise<PlanResult> {
  return camelize<PlanResult>(await apiRequest("/capping/planner/plan", { method: "POST", body: req }));
}

/** The same calculation as an Excel workbook. */
export async function downloadPlan(req: PlanRequest): Promise<void> {
  const blob = await apiBlob("/capping/planner/export", { method: "POST", body: req });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `smart-capping-plan-${req.month}.xlsx`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 30_000);
}
