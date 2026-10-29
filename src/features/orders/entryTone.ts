import type { EntryTone } from "@/types/order";

/**
 * The colour of a day's number, set by the server (see `entry_tone` in order_service.py): who set it, and for a Data Entry person's own number how many times
 * it has been changed. `rgb` is the colour as "r g b" for a tinted background; `text` / `border` are the classes for the number and the edge.
 * The administrator colour is violet on purpose: yellow already means "changed once", and orange sits too close to red.
 */
export const ENTRY_TONES: Record<EntryTone, { label: string; rgb: string; text: string; border: string }> = {
  l1_first: { label: "First entry by Data Entry", rgb: "var(--success)", text: "text-status-success", border: "border-status-success/30" },
  l1_second: { label: "Changed once", rgb: "234 179 8", text: "text-yellow-700 dark:text-yellow-300", border: "border-yellow-500/40" },
  l1_third: { label: "Changed twice or more", rgb: "var(--danger)", text: "text-status-danger", border: "border-status-danger/30" },
  l2: { label: "Team Lead", rgb: "var(--info)", text: "text-status-info", border: "border-status-info/30" },
  admin: { label: "Reviewer / Admin / Developer", rgb: "139 92 246", text: "text-violet-700 dark:text-violet-300", border: "border-violet-500/40" },
};

export const ENTRY_TONE_ORDER: EntryTone[] = ["l1_first", "l1_second", "l1_third", "l2", "admin"];
