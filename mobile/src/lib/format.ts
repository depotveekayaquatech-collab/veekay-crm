export function isoDate(d: Date): string {
  const off = d.getTimezoneOffset();
  return new Date(d.getTime() - off * 60000).toISOString().slice(0, 10);
}

export function daysAgo(n: number): string {
  const d = new Date();
  d.setDate(d.getDate() - n);
  return isoDate(d);
}

const local = (iso: string) => (/^\d{4}-\d{2}-\d{2}$/.test(iso) ? new Date(`${iso}T00:00:00`) : new Date(iso));

export const fmtDate = (iso: string) => local(iso).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });
export const fmtDateTime = (iso: string) => local(iso).toLocaleString("en-IN", { day: "numeric", month: "short", hour: "numeric", minute: "2-digit" });
export const fmtMonth = (iso: string) => new Date(`${iso.slice(0, 7)}-01T00:00:00`).toLocaleDateString("en-IN", { month: "long", year: "numeric" });
export const fmtMoney = (n: number) => `₹${n.toLocaleString("en-IN", { minimumFractionDigits: n % 1 ? 2 : 0, maximumFractionDigits: 2 })}`;
export const fmtNumber = (n: number) => n.toLocaleString("en-IN");

/** What was done to an entry after it was saved: the person (name and role), the time, and from what to what. */
export interface EntryChange { by_name: string | null; by_role_label: string; at: string; old_count: number; new_count: number; reason: string | null }
export interface EntryStatus { status: "submitted" | "verified_l2" | "reviewed_l3"; label: string; by_name: string | null; at: string | null }

/** "Changed by Rahul – Team Lead, 24 Oct 2026, 4:10 PM". */
export function changedByLine(c: EntryChange): string {
  const d = new Date(c.at);
  const date = d.toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });
  const time = d.toLocaleTimeString("en-IN", { hour: "numeric", minute: "2-digit", hour12: true }).toUpperCase();
  return `Changed by ${c.by_name ?? "a senior colleague"} – ${c.by_role_label}, ${date}, ${time}`;
}

/** The same, with the old and new number and the reason: for the alert that opens when a changed day is tapped. */
export function changedDetail(c: EntryChange): string {
  return `${changedByLine(c)}.\nWas ${c.old_count}, now ${c.new_count} bottles${c.reason ? `.\nReason: ${c.reason}` : ""}`;
}

export function fmtSize(bytes: number): string {
  return bytes < 1024 * 1024 ? `${Math.max(1, Math.round(bytes / 1024))} KB` : `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

export function titleCase(s: string): string {
  return s.replace(/_/g, " ").toLowerCase().replace(/^\w|\s\w/g, (c) => c.toUpperCase());
}

/** Names come in as typed in the sheet, often ALL CAPS: show those in normal capitals. */
export function niceName(name: string): string {
  return name === name.toUpperCase() ? name.toLowerCase().replace(/(^|[\s.'-])([a-z])/g, (_m, p: string, c: string) => p + c.toUpperCase()) : name;
}

export function recentMonths(n = 12): { value: string; label: string }[] {
  const out: { value: string; label: string }[] = [];
  const d = new Date();
  d.setDate(1);
  for (let i = 0; i < n; i++) {
    const value = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
    out.push({ value, label: fmtMonth(`${value}-01`) });
    d.setMonth(d.getMonth() - 1);
  }
  return out;
}
