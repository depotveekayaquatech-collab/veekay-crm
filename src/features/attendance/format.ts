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
