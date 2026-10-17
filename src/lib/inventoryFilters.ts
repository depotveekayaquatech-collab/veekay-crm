/**
 * Linked Region / State / City / Vendor filters for the Inventory page.
 *
 * Every dropdown only offers values that still have stores once the OTHER three selections are applied, so the lists
 * always agree with each other (pick a state and the city list shrinks to that state's cities). A selection that stops
 * making sense after another one changes is cleared instead of leaving the list empty.
 */
export type LocationKey = "region" | "state" | "city" | "vendor";
export type LocationFilters = Record<LocationKey, string>;
export interface LocationOption { value: string; count: number }

export interface LocationRow {
  regionName: string | null;
  state: string | null;
  city: string | null;
  vendorName: string | null;
}

export const KEYS: LocationKey[] = ["region", "state", "city", "vendor"];
export const NO_FILTERS: LocationFilters = { region: "", state: "", city: "", vendor: "" };

const FIELD: Record<LocationKey, (r: LocationRow) => string | null> = {
  region: (r) => r.regionName,
  state: (r) => r.state,
  city: (r) => r.city,
  vendor: (r) => r.vendorName,
};

const norm = (v: string | null | undefined) => (v ?? "").trim().toLowerCase();

/** True when the row passes every selected filter, optionally ignoring one (used to build that filter's own list). */
function passes(row: LocationRow, f: LocationFilters, skip?: LocationKey): boolean {
  return KEYS.every((k) => k === skip || !f[k] || norm(FIELD[k](row)) === norm(f[k]));
}

export const hasFilters = (f: LocationFilters) => KEYS.some((k) => !!f[k]);

export function applyLocationFilters<T extends LocationRow>(rows: T[], f: LocationFilters): T[] {
  return hasFilters(f) ? rows.filter((r) => passes(r, f)) : rows;
}

/** The choices for one dropdown (with how many stores each would show), A to Z. Stores without a value are not listed. */
export function optionsFor(rows: LocationRow[], f: LocationFilters, key: LocationKey): LocationOption[] {
  const seen = new Map<string, { value: string; count: number }>();
  for (const r of rows) {
    if (!passes(r, f, key)) continue;
    const label = (FIELD[key](r) ?? "").trim();
    if (!label) continue;
    const id = label.toLowerCase();
    const hit = seen.get(id);
    if (hit) hit.count++;
    else seen.set(id, { value: label, count: 1 });
  }
  return [...seen.values()].sort((a, b) => a.value.localeCompare(b.value, undefined, { sensitivity: "base" }));
}

/**
 * Clears any selection that no longer has a store behind it (for example a city after the state was changed).
 * `keep` is the dropdown the person just used: it always wins, the other selections give way to it.
 */
export function pruneFilters(rows: LocationRow[], f: LocationFilters, keep?: LocationKey): LocationFilters {
  let cur = f;
  for (let pass = 0; pass < KEYS.length; pass++) {
    let changed = false;
    const next = { ...cur };
    for (const k of KEYS) {
      if (k !== keep && next[k] && !optionsFor(rows, next, k).some((o) => norm(o.value) === norm(next[k]))) {
        next[k] = "";
        changed = true;
      }
    }
    cur = next;
    if (!changed) break;
  }
  return cur;
}

/** The filters after the person picks `value` in one dropdown ("" = all). */
export function setFilter(rows: LocationRow[], f: LocationFilters, key: LocationKey, value: string): LocationFilters {
  return pruneFilters(rows, { ...f, [key]: value }, key);
}
