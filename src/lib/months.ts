const NAMES = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];

/** "2026-09" -> "September 2026" */
export function monthLabel(ym: string): string {
  const [y, m] = ym.split("-").map(Number);
  return y && m ? `${NAMES[m - 1]} ${y}` : ym;
}

/**
 * Selectable compliance months, newest first: back to 2026-06 and at most 12 months.
 * Mirrors COMPLIANCE_EARLIEST_MONTH / COMPLIANCE_MAX_MONTHS_BACK on the server.
 */
export function complianceMonths(now = new Date()): string[] {
  const out: string[] = [];
  let y = now.getFullYear();
  let m = now.getMonth() + 1;
  for (let i = 0; i <= 12; i++) {
    const key = `${y}-${String(m).padStart(2, "0")}`;
    if (key < "2026-06") break;
    out.push(key);
    m -= 1;
    if (m === 0) {
      y -= 1;
      m = 12;
    }
  }
  return out.length ? out : [`${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`];
}

/** The last `n` months (current first), no floor — used for printing cards. */
export function recentMonths(n: number, now = new Date()): string[] {
  const out: string[] = [];
  let y = now.getFullYear();
  let m = now.getMonth() + 1;
  for (let i = 0; i < n; i++) {
    out.push(`${y}-${String(m).padStart(2, "0")}`);
    m -= 1;
    if (m === 0) {
      y -= 1;
      m = 12;
    }
  }
  return out;
}
