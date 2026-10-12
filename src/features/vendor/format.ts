export function fmtDate(iso: string): string {
  const d = /^\d{4}-\d{2}-\d{2}$/.test(iso) ? new Date(`${iso}T00:00:00`) : new Date(iso);
  return d.toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });
}

export function fmtDateTime(iso: string): string {
  return new Date(iso).toLocaleString("en-IN", { day: "numeric", month: "short", hour: "numeric", minute: "2-digit" });
}

export function fmtMonth(iso: string): string {
  return new Date(`${iso.slice(0, 7)}-01T00:00:00`).toLocaleDateString("en-IN", { month: "long", year: "numeric" });
}

export function fmtSize(bytes: number): string {
  return bytes < 1024 * 1024 ? `${Math.max(1, Math.round(bytes / 1024))} KB` : `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

/** Names come in as typed in the sheet, often ALL CAPS: show those in normal capitals. */
export function niceName(name: string): string {
  return name === name.toUpperCase() ? name.toLowerCase().replace(/(^|[\s.'-])([a-z])/g, (_, p: string, c: string) => p + c.toUpperCase()) : name;
}

export function titleCase(s: string): string {
  return s.replace(/_/g, " ").toLowerCase().replace(/^\w|\s\w/g, (c) => c.toUpperCase());
}

/** "2026-09" for the month containing today, going back n months. */
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
