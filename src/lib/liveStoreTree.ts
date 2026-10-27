/**
 * The Vendors page's "Live stores in depth": live stores grouped place by place, with how many stores and vendors each place has.
 * Zepto is grouped State > City, Blinkit Region > State > City. Spellings that differ only by case or spacing ("DElhi", "Delhi") are one place,
 * shown the way most of its stores spell it. Only LIVE stores count.
 */
export type TreeLevel = "region" | "state" | "city";

export interface TreeSource {
  platformSlug: string | null;
  status: string;
  regionName: string | null;
  state: string | null;
  city: string | null;
  vendorName: string | null;
  pendingDays: number;
  markedToday: boolean;
  monthBottles: number;
}

export interface TreeNode {
  id: string;
  level: TreeLevel;
  label: string;
  /** The places from the top down to this one, for turning a click into filters. A place with no value cannot be filtered on (value ""). */
  path: { level: TreeLevel; value: string }[];
  stores: number;
  vendors: number;
  behind: number;
  markedToday: number;
  bottles: number;
  children: TreeNode[];
}

export interface TreeTotals { stores: number; vendors: number; states: number; cities: number; behind: number; markedToday: number; bottles: number }

export const NOT_SET = "Not set";
const LEVELS: Record<string, TreeLevel[]> = { zepto: ["state", "city"], blinkit: ["region", "state", "city"] };
const DEFAULT_LEVELS: TreeLevel[] = ["state", "city"];

export const levelsFor = (platformSlug: string | null | undefined): TreeLevel[] => LEVELS[(platformSlug ?? "").toLowerCase()] ?? DEFAULT_LEVELS;
export const LEVEL_LABEL: Record<TreeLevel, string> = { region: "Region", state: "State", city: "City" };

const clean = (v: string | null | undefined) => (v ?? "").replace(/\s+/g, " ").trim();
const FIELD: Record<TreeLevel, (s: TreeSource) => string | null> = { region: (s) => s.regionName, state: (s) => s.state, city: (s) => s.city };
const byText = (a: string, b: string) => a.localeCompare(b, undefined, { sensitivity: "base" });

const isLive = (s: TreeSource) => s.status === "LIVE";

function vendorCount(items: TreeSource[]): number {
  return new Set(items.map((s) => clean(s.vendorName).toLowerCase()).filter(Boolean)).size;
}

function group(items: TreeSource[], levels: TreeLevel[], depth: number, parent: TreeNode["path"], parentId: string): TreeNode[] {
  if (depth >= levels.length) return [];
  const level = levels[depth];
  const buckets = new Map<string, { spellings: Map<string, number>; items: TreeSource[] }>();
  for (const s of items) {
    const label = clean(FIELD[level](s));
    const key = label.toLowerCase();
    const b = buckets.get(key) ?? { spellings: new Map<string, number>(), items: [] };
    b.spellings.set(label, (b.spellings.get(label) ?? 0) + 1);
    b.items.push(s);
    buckets.set(key, b);
  }
  return [...buckets.entries()]
    .map(([key, b]) => {
      const label = [...b.spellings.entries()].sort((x, y) => y[1] - x[1])[0][0];           // the spelling most of its stores use
      const path = [...parent, { level, value: label }];
      const id = `${parentId}/${level}:${key}`;
      return {
        id, level, label: label || NOT_SET, path,
        stores: b.items.length,
        vendors: vendorCount(b.items),
        behind: b.items.filter((s) => s.pendingDays > 0).length,
        markedToday: b.items.filter((s) => s.markedToday).length,
        bottles: b.items.reduce((n, s) => n + s.monthBottles, 0),
        children: group(b.items, levels, depth + 1, path, id),
      };
    })
    .sort((a, b) => b.stores - a.stores || byText(a.label, b.label));
}

/** The place tree for one platform's live stores (the stores passed in should already be that platform's). */
export function buildTree(items: TreeSource[], levels: TreeLevel[]): TreeNode[] {
  return group(items.filter(isLive), levels, 0, [], "");
}

export function summarize(items: TreeSource[]): TreeTotals {
  const live = items.filter(isLive);
  const states = new Set(live.map((s) => clean(s.state).toLowerCase()).filter(Boolean));
  const cities = new Set(live.filter((s) => clean(s.city)).map((s) => `${clean(s.state).toLowerCase()}|${clean(s.city).toLowerCase()}`));
  return {
    stores: live.length, vendors: vendorCount(live), states: states.size, cities: cities.size,
    behind: live.filter((s) => s.pendingDays > 0).length, markedToday: live.filter((s) => s.markedToday).length,
    bottles: live.reduce((n, s) => n + s.monthBottles, 0),
  };
}

/** The tree as a visible list: a node's children follow it while it is expanded. */
export function visibleRows(nodes: TreeNode[], expanded: ReadonlySet<string>, depth = 0): { node: TreeNode; depth: number }[] {
  return nodes.flatMap((n) => [{ node: n, depth }, ...(expanded.has(n.id) ? visibleRows(n.children, expanded, depth + 1) : [])]);
}

/** Every node id that has children (for "Expand all"). */
export function expandableIds(nodes: TreeNode[]): string[] {
  return nodes.flatMap((n) => (n.children.length ? [n.id, ...expandableIds(n.children)] : []));
}

/** One row per deepest place, each carrying its full path (for the CSV). */
export function leafRows(nodes: TreeNode[]): TreeNode[] {
  return nodes.flatMap((n) => (n.children.length ? leafRows(n.children) : [n]));
}
