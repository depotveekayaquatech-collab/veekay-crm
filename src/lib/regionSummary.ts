/**
 * One row per Region / State / City for a single platform: how many different vendors and how many stores.
 * Used by the Inventory page's "Blinkit - North & South" table.
 */
export interface SummarySource {
  platformSlug: string | null;
  regionName: string | null;
  state: string | null;
  city: string | null;
  vendorName: string | null;
}

export interface CityRow { region: string; state: string; city: string; vendors: number; stores: number }
export interface RegionTotal { region: string; vendors: number; stores: number }
export interface RegionSummary { rows: CityRow[]; regions: RegionTotal[]; total: { vendors: number; stores: number } }

const UNSET = "Not set";
const clean = (v: string | null | undefined) => (v ?? "").trim();
const key = (v: string) => v.toLowerCase();
const byText = (a: string, b: string) => a.localeCompare(b, undefined, { sensitivity: "base" });

export function summarizeByCity(items: SummarySource[], opts: { platformSlug: string; regions: string[] }): RegionSummary {
  const wanted = opts.regions.map((r) => key(r.trim()));
  const regionLabel = new Map<string, string>();       // lower-case region -> label as first seen
  const cities = new Map<string, { region: string; state: string; city: string; stores: number; vendors: Set<string> }>();
  const perRegion = new Map<string, { stores: number; vendors: Set<string> }>();
  const all = new Set<string>();
  let stores = 0;

  for (const s of items) {
    if (s.platformSlug !== opts.platformSlug) continue;
    const rk = key(clean(s.regionName));
    if (!wanted.includes(rk)) continue;
    const region = regionLabel.get(rk) ?? (regionLabel.set(rk, clean(s.regionName)), clean(s.regionName));
    const state = clean(s.state) || UNSET;
    const city = clean(s.city) || UNSET;
    const vendor = key(clean(s.vendorName));

    const ck = `${rk}|${key(state)}|${key(city)}`;
    const c = cities.get(ck) ?? { region, state, city, stores: 0, vendors: new Set<string>() };
    c.stores++;
    if (vendor) c.vendors.add(vendor);
    cities.set(ck, c);

    const r = perRegion.get(rk) ?? { stores: 0, vendors: new Set<string>() };
    r.stores++;
    if (vendor) r.vendors.add(vendor);
    perRegion.set(rk, r);

    if (vendor) all.add(vendor);
    stores++;
  }

  // North first, then South: the order the regions were asked for, not alphabetical
  const order = (region: string) => wanted.indexOf(key(region));
  const rows = [...cities.values()]
    .sort((a, b) => order(a.region) - order(b.region) || byText(a.state, b.state) || byText(a.city, b.city))
    .map((c) => ({ region: c.region, state: c.state, city: c.city, vendors: c.vendors.size, stores: c.stores }));
  const regions = wanted
    .filter((rk) => perRegion.has(rk))
    .map((rk) => ({ region: regionLabel.get(rk) ?? rk, vendors: perRegion.get(rk)!.vendors.size, stores: perRegion.get(rk)!.stores }));
  return { rows, regions, total: { vendors: all.size, stores } };
}
