import { monthLabel } from "@/lib/months";
import type { VendorChoice } from "@/features/vendorpay/api";

export const DISPLAY_TIME_ZONE = "Asia/Kolkata";
const MONTH_PATTERN = /^\d{4}-(0[1-9]|1[0-2])$/;
export const MONTHS_OFFERED = 36;

export const isMonth = (value: string | null | undefined): value is string => Boolean(value && MONTH_PATTERN.test(value));

/** The current month as YYYY-MM on the India clock (the same clock the server uses), whatever the browser's time zone is. */
export function currentMonthIst(now: Date = new Date()): string {
  const parts = new Intl.DateTimeFormat("en-CA", { timeZone: DISPLAY_TIME_ZONE, year: "numeric", month: "2-digit" }).formatToParts(now);
  const get = (type: string) => parts.find((p) => p.type === type)?.value ?? "";
  return `${get("year")}-${get("month")}`;
}

/** YYYY-MM moved by `delta` months (negative = earlier). */
export function shiftMonth(month: string, delta: number): string {
  const [y, m] = month.split("-").map(Number);
  const index = y * 12 + (m - 1) + delta;
  return `${Math.floor(index / 12)}-${String((index % 12) + 1).padStart(2, "0")}`;
}

/** Months for the picker, newest first, always including `selected` even if it is older than the window. */
export function monthOptions(current: string, selected: string, count = MONTHS_OFFERED): { value: string; label: string }[] {
  const months = Array.from({ length: count }, (_, i) => shiftMonth(current, -i));
  if (!months.includes(selected)) months.push(selected);
  return months.map((value) => ({ value, label: monthLabel(value) }));
}

export const vendorLabel = (v: VendorChoice) => `${v.name}${v.city ? `, ${v.city}` : ""} (${v.vendorCode})`;

/** "3 Nov 2026, 6:47 pm" in India time. */
export const formatWhen = (iso: string) =>
  new Date(iso).toLocaleString("en-IN", { timeZone: DISPLAY_TIME_ZONE, day: "numeric", month: "short", year: "numeric", hour: "numeric", minute: "2-digit", hour12: true });

/** "5 Oct 2026" from a plain YYYY-MM-DD date (no time-zone shifting). */
export const formatDay = (iso: string) =>
  new Date(`${iso}T12:00:00`).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });

export function ageText(minutes: number): string {
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes} minute${minutes === 1 ? "" : "s"} ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 48) return `${hours} hour${hours === 1 ? "" : "s"} ago`;
  return `${Math.floor(hours / 24)} days ago`;
}
