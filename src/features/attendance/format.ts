export function fmtTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

export function fmtMinutes(m: number): string {
  if (!m) return "0m";
  const h = Math.floor(m / 60);
  const r = m % 60;
  return h ? (r ? `${h}h ${r}m` : `${h}h`) : `${r}m`;
}

export function fmtDay(iso: string): string {
  return new Date(`${iso}T12:00:00`).toLocaleDateString(undefined, { weekday: "short", day: "2-digit", month: "short" });
}

export const AWAY_TEXT = "Away (not from office)";

/** "At office" or "Away (not from office)". Anything not verified at an office (outside it, or no location shared) is away. */
export function presenceText(loc: { status: string } | null | undefined): string {
  if (!loc) return "";
  return loc.status === "office" ? "At office" : AWAY_TEXT;
}

/** For the sheet: the office name when at an office, otherwise the coordinates ("12.927611, 80.194880"). */
export function locationText(loc: { status: string; label?: string; latitude?: number; longitude?: number } | null | undefined): string {
  if (!loc) return "";
  if (loc.status === "office") return loc.label ?? "Office";
  if (loc.latitude != null && loc.longitude != null) return `${loc.latitude.toFixed(6)}, ${loc.longitude.toFixed(6)}`;
  return "Location not shared";
}
