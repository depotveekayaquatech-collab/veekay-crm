import type { PlanRequest, PlannerMode, PlannerProject } from "@/services/cappingPlanner";

/** A whole number typed into a field: "" is blank, anything but digits is invalid. Commas and spaces (50,000) are allowed. */
export function parseCount(text: string): { value: number | null; error: string | null } {
  const t = text.replace(/[,\s]/g, "");
  if (t === "") return { value: null, error: null };
  if (!/^\d+$/.test(t)) return { value: null, error: "Enter a whole number." };
  const n = Number(t);
  return Number.isSafeInteger(n) ? { value: n, error: null } : { value: null, error: "That number is too large." };
}

/** The pasted lines that are not blank, trimmed, in the order pasted. */
export function priorityLines(text: string): string[] {
  return text.split(/\r?\n/).map((l) => l.trim()).filter(Boolean);
}

/** Removes the n-th pasted (non-blank) line, 1-based, and keeps the others in their order. */
export function removePriorityLine(text: string, position: number): string {
  return priorityLines(text).filter((_, i) => i + 1 !== position).join("\n");
}

export interface PlannerForm {
  month: string;
  project: PlannerProject;
  mode: PlannerMode;
  storeLimitText: string;
  targetText: string;
  priorityText: string;
}

/** The request for a form, or the problem with each field. The store limit must be 1 or more when given (blank = every eligible store); a blank target is 0. */
export function buildRequest(f: PlannerForm): { request: PlanRequest | null; errors: { storeLimit?: string; target?: string } } {
  const limit = parseCount(f.storeLimitText);
  const target = parseCount(f.targetText);
  const errors: { storeLimit?: string; target?: string } = {};
  if (limit.error) errors.storeLimit = limit.error;
  else if (limit.value !== null && (limit.value < 1 || limit.value > 100_000)) errors.storeLimit = "Use a number from 1 to 100,000, or leave it blank for every eligible store.";
  if (target.error) errors.target = target.error;
  else if (target.value !== null && target.value > 100_000_000) errors.target = "That target is too large.";
  if (errors.storeLimit || errors.target) return { request: null, errors };
  return {
    request: { month: f.month, project: f.project, mode: f.mode, storeLimit: limit.value, target: target.value ?? 0, priority: priorityLines(f.priorityText) },
    errors,
  };
}
