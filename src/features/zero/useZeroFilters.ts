import { useCallback, useMemo } from "react";
import { useSearchParams } from "react-router-dom";
import type { Mode, ZeroFilterValues } from "@/features/zero/api";

const ZONE = "Asia/Kolkata";
const STORE_KEY = "zero-review.filters";

/** Today in India as YYYY-MM-DD (every date boundary in this module is Asia/Kolkata, whatever the browser's zone). */
export const todayIST = (): string => new Date().toLocaleDateString("en-CA", { timeZone: ZONE });

const parse = (iso: string) => new Date(`${iso}T12:00:00`);
export const fmt = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
export const addDays = (iso: string, n: number) => { const d = parse(iso); d.setDate(d.getDate() + n); return fmt(d); };
export const mondayOf = (iso: string) => addDays(iso, -((parse(iso).getDay() + 6) % 7));
export const monthOf = (iso: string) => iso.slice(0, 7);
export const shiftMonth = (ym: string, by: number) => { const [y, m] = ym.split("-").map(Number); const d = new Date(y, m - 1 + by, 1); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`; };
export const monthEnd = (ym: string) => { const [y, m] = ym.split("-").map(Number); return fmt(new Date(y, m, 0)); };

export type Preset = "this-week" | "last-week" | "this-month" | "last-month" | "custom";
export const PRESETS: { value: Preset; label: string }[] = [
  { value: "this-week", label: "This Week" }, { value: "last-week", label: "Last Week" },
  { value: "this-month", label: "This Month" }, { value: "last-month", label: "Last Month" }, { value: "custom", label: "Custom" },
];

export function presetRange(p: Exclude<Preset, "custom">): { from: string; to: string } {
  const t = todayIST();
  if (p === "this-week") return { from: mondayOf(t), to: t };
  if (p === "last-week") { const m = addDays(mondayOf(t), -7); return { from: m, to: addDays(m, 6) }; }
  if (p === "this-month") return { from: `${monthOf(t)}-01`, to: t };
  const prev = shiftMonth(monthOf(t), -1);
  return { from: `${prev}-01`, to: monthEnd(prev) };
}

const list = (v: string | null) => (v ? v.split(",").filter(Boolean) : []);
const MODES: Mode[] = ["break", "ignore", "count"];

/**
 * The filters of every Zero Review sub-tab. They live in the URL query string (so a view can be bookmarked or sent to a team lead) and are remembered for
 * the rest of the session, so coming back to the tab opens where the person left off.
 */
export function useZeroFilters() {
  const [params, setParams] = useSearchParams();

  const saved = useMemo(() => {
    try { return new URLSearchParams(sessionStorage.getItem(STORE_KEY) ?? ""); } catch { return new URLSearchParams(); }
  }, []);
  // a URL with no filter in it opens with the last-used ones
  const src = ["from", "to", "preset", "region", "employee", "platform", "q", "status", "n", "unmarked", "ugt", "sort"].some((k) => params.has(k)) ? params : saved;

  const preset = (src.get("preset") as Preset | null) ?? "this-week";
  const range = preset !== "custom" ? presetRange(preset) : { from: src.get("from") ?? presetRange("this-week").from, to: src.get("to") ?? todayIST() };
  const mode = src.get("unmarked") as Mode | null;
  const values: ZeroFilterValues = {
    from: range.from, to: range.to, regions: list(src.get("region")), employees: list(src.get("employee")), platform: src.get("platform") ?? "", q: src.get("q") ?? "",
    status: (src.get("status") as ZeroFilterValues["status"]) ?? "", n: Number(src.get("n") ?? 0) || 0, unmarked: mode && MODES.includes(mode) ? mode : "break",
    unmarkedGe: Number(src.get("ugt") ?? 0) || 0, sort: src.get("sort") ?? "streak",
  };

  const patch = useCallback((changes: Record<string, string | undefined>) => {
    const next = new URLSearchParams(params);
    // fold the remembered filters in first, so changing one keeps the rest
    if (!["from", "to", "preset", "region", "employee", "platform", "q", "status", "n", "unmarked", "ugt", "sort"].some((k) => next.has(k))) saved.forEach((v, k) => next.set(k, v));
    for (const [k, v] of Object.entries(changes)) { if (v === undefined || v === "") next.delete(k); else next.set(k, v); }
    next.delete("page");
    setParams(next, { replace: true });
    try {
      const keep = new URLSearchParams();
      next.forEach((v, k) => { if (!["tab", "page", "week", "thr", "month", "drawer"].includes(k)) keep.set(k, v); });
      sessionStorage.setItem(STORE_KEY, keep.toString());
    } catch { /* storage blocked: the URL still carries the filters */ }
  }, [params, saved, setParams]);

  return {
    values, preset, params, patch, setParams,
    setPreset: (p: Preset) => patch(p === "custom" ? { preset: p, from: values.from, to: values.to } : { preset: p, from: undefined, to: undefined }),
    clear: () => { const next = new URLSearchParams(); const tab = params.get("tab"); if (tab) next.set("tab", tab); try { sessionStorage.removeItem(STORE_KEY); } catch { /* ignore */ } setParams(next, { replace: true }); },
  };
}
