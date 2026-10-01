/** "3h ago", "2d ago" — short, for table cells. */
export function timeAgo(iso: string): string {
  const mins = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 60_000));
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.round(mins / 60);
  if (hours < 48) return `${hours}h ago`;
  return `${Math.round(hours / 24)}d ago`;
}

/** Time left (or past) against the ticket's SLA deadline. */
export function dueLabel(dueAt: string | null): { text: string; late: boolean } | null {
  if (!dueAt) return null;
  const mins = Math.round((new Date(dueAt).getTime() - Date.now()) / 60_000);
  const abs = Math.abs(mins);
  const span = abs < 60 ? `${abs}m` : abs < 48 * 60 ? `${Math.round(abs / 60)}h` : `${Math.round(abs / 1440)}d`;
  return mins < 0 ? { text: `${span} overdue`, late: true } : { text: `due in ${span}`, late: false };
}
