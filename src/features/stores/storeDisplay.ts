import type { Store } from "@/types/store";

/** How a store's status reads on screen, shared by the card and the table so the two never disagree. */
export const STATUS: Record<Store["status"], { label: string; tone: "success" | "warning" | "neutral" }> = {
  LIVE: { label: "Live", tone: "success" },
  PENDING: { label: "Pending", tone: "warning" },
  CLOSE: { label: "Closed", tone: "neutral" },
};

export const platformTone = (slug: string | null) => (slug === "blinkit" ? "success" : slug === "zepto" ? "info" : "neutral");
