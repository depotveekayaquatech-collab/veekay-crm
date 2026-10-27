import { useMemo, useState } from "react";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/feedback/EmptyState";
import { IconChevronRight, IconDownload } from "@/components/ui/icons";
import { downloadCsv } from "@/lib/csv";
import {
  LEVEL_LABEL, buildTree, expandableIds, leafRows, levelsFor, summarize, visibleRows,
  type TreeLevel, type TreeNode, type TreeSource,
} from "@/lib/liveStoreTree";

type Item = TreeSource & { platform: string | null };

const PLATFORM_ORDER = ["zepto", "blinkit"];
const platformRank = (slug: string) => (PLATFORM_ORDER.includes(slug) ? PLATFORM_ORDER.indexOf(slug) : PLATFORM_ORDER.length);

/**
 * Live stores in depth: Zepto place by place (State > City), Blinkit region by region (Region > State > City), with the number of live stores and of
 * vendors in each. It is fed the stores the page's filters leave (platform, region, state, city, vendor, status chips, search), so every number follows
 * whatever is selected. Clicking a place applies it as a filter.
 */
export function LiveStoresExplorer({
  items, filterActive, isPicked, onPick, onClear,
}: {
  items: Item[];
  filterActive: boolean;
  /** True when every level of this place is already a selected filter. */
  isPicked: (path: TreeNode["path"]) => boolean;
  onPick: (path: TreeNode["path"]) => void;
  onClear: () => void;
}) {
  const live = useMemo(() => items.filter((s) => s.status === "LIVE"), [items]);
  const platforms = useMemo(() => {
    const seen = new Map<string, string>();
    for (const s of live) if (s.platformSlug) seen.set(s.platformSlug, s.platform ?? s.platformSlug);
    return [...seen.entries()].sort((a, b) => platformRank(a[0]) - platformRank(b[0]) || a[1].localeCompare(b[1])).map(([slug, name]) => ({ slug, name }));
  }, [live]);

  const [chosen, setChosen] = useState("");
  const slug = platforms.some((p) => p.slug === chosen) ? chosen : platforms[0]?.slug ?? "";   // the first platform that still has live stores
  const mine = useMemo(() => live.filter((s) => s.platformSlug === slug), [live, slug]);
  const levels = levelsFor(slug);
  const tree = useMemo(() => buildTree(mine, levels), [mine, levels]);
  const totals = useMemo(() => summarize(mine), [mine]);

  const [open, setOpen] = useState<Set<string>>(new Set());
  const [openAll, setOpenAll] = useState(false);
  const topIds = useMemo(() => tree.filter((n) => n.children.length).map((n) => n.id), [tree]);
  const allIds = useMemo(() => expandableIds(tree), [tree]);
  // nothing opened yet: show the top level's places so the next level is one click away; "Expand all" opens every level
  const expanded = useMemo(() => (openAll ? new Set(allIds) : open.size ? open : new Set(levels.length > 2 ? topIds : [])), [openAll, allIds, open, levels.length, topIds]);
  const rows = useMemo(() => visibleRows(tree, expanded), [tree, expanded]);

  const toggle = (id: string) => {
    setOpenAll(false);
    setOpen(() => {
      const next = new Set(expanded);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next.size ? next : new Set([""]);          // a non-empty set means "the person chose", even when everything is closed
    });
  };

  const name = platforms.find((p) => p.slug === slug)?.name ?? "";
  const topLabel = LEVEL_LABEL[levels[0]];
  const csv = () =>
    downloadCsv(
      `live-stores-${slug || "all"}-${new Date().toISOString().slice(0, 10)}.csv`,
      ["Platform", ...levels.map((l) => LEVEL_LABEL[l]), "Live stores", "Vendors", "Behind schedule", "Marked today", "Bottles (month)"],
      [
        ...leafRows(tree).map((n) => [name, ...levels.map((l) => n.path.find((p) => p.level === l)?.value ?? ""), n.stores, n.vendors, n.behind, n.markedToday, n.bottles]),
        ["Total", ...levels.map(() => ""), totals.stores, totals.vendors, totals.behind, totals.markedToday, totals.bottles],
      ],
    );

  const kpis: { label: string; value: number }[] = [
    { label: "Live stores", value: totals.stores },
    { label: "Vendors", value: totals.vendors },
    { label: "States", value: totals.states },
    { label: "Cities", value: totals.cities },
  ];

  return (
    <section className="overflow-hidden rounded-xl border border-surface-border bg-surface shadow-card" aria-labelledby="live-stores-title">
      <div className="flex flex-wrap items-center gap-3 border-b border-surface-border/80 bg-surface-subtle px-5 py-3.5">
        <div className="min-w-0">
          <h2 id="live-stores-title" className="text-sm font-bold text-gray-900">Live stores in depth</h2>
          <p className="text-xs text-gray-500">
            {slug === "blinkit" ? "Region, then state, then city" : "State, then city"}. Every number follows the filters{filterActive ? " you have selected" : " (none selected: all live stores)"}. Click a place to filter to it.
          </p>
        </div>
        <div className="ml-auto flex flex-wrap items-center gap-2">
          {filterActive && <button onClick={onClear} className="rounded-lg px-3 py-2 text-sm font-semibold text-brand-600 hover:bg-brand-50">Clear filters</button>}
          <Button variant="secondary" disabled={!tree.length} onClick={csv}>
            <IconDownload className="h-4 w-4" />
            Export CSV
          </Button>
        </div>
      </div>

      {platforms.length > 1 && (
        <div role="tablist" aria-label="Platform" className="flex flex-wrap gap-1.5 border-b border-surface-border/80 px-5 py-3">
          {platforms.map((p) => (
            <button key={p.slug} role="tab" aria-selected={slug === p.slug} onClick={() => setChosen(p.slug)}
              className={`rounded-lg px-3.5 py-1.5 text-sm font-semibold transition-colors ${slug === p.slug ? "bg-brand-500 text-white shadow-sm" : "bg-surface text-gray-600 ring-1 ring-surface-border hover:bg-surface-subtle"}`}>
              {p.name}
            </button>
          ))}
        </div>
      )}

      {!tree.length ? (
        <div className="p-5"><EmptyState title="No live stores here" description={filterActive ? "No live store matches the filters. Clear a filter to see more." : "There are no live stores yet."} /></div>
      ) : (
        <>
          <div className="grid grid-cols-2 gap-3 px-5 py-4 lg:grid-cols-4" aria-live="polite">
            {kpis.map((k) => (
              <div key={k.label} className="rounded-lg border border-surface-border bg-surface px-4 py-3">
                <p className="text-[11px] font-bold uppercase tracking-wider text-gray-500">{k.label}{name ? ` · ${name}` : ""}</p>
                <p className="mt-1 text-2xl font-bold tabular-nums text-heading">{k.value.toLocaleString("en-IN")}</p>
              </div>
            ))}
          </div>

          <div className="flex items-center justify-between gap-3 px-5 pb-2 text-xs text-gray-500">
            <span>{tree.length} {topLabel.toLowerCase()}{tree.length === 1 ? "" : "s"}</span>
            {allIds.length > 0 && (
              <button className="font-semibold text-brand-600 hover:text-brand-700" onClick={() => { setOpenAll((v) => !v); setOpen(new Set([""])); }}>
                {openAll ? "Collapse all" : "Expand all"}
              </button>
            )}
          </div>

          <div className="max-h-[34rem] overflow-auto">
            <table className="w-full min-w-[620px] text-sm">
              <thead className="sticky top-0 z-10 bg-surface">
                <tr className="border-y border-surface-border text-left text-[11px] font-bold uppercase tracking-wider text-gray-500">
                  <th className="px-5 py-2.5">Place</th>
                  <th className="px-3 py-2.5 text-right">Live stores</th>
                  <th className="px-3 py-2.5 text-right">Vendors</th>
                  <th className="px-3 py-2.5 text-right">Behind</th>
                  <th className="px-3 py-2.5 text-right">Marked today</th>
                  <th className="px-3 py-2.5 text-right">Bottles (month)</th>
                  <th className="px-5 py-2.5 text-right"><span className="sr-only">Filter</span></th>
                </tr>
              </thead>
              <tbody>
                {rows.map(({ node, depth }) => {
                  const picked = isPicked(node.path);
                  const canPick = node.path.every((p) => p.value !== "");
                  return (
                    <tr key={node.id} className={`border-t border-surface-border/70 ${picked ? "bg-brand-50/60" : ""}`}>
                      <td className="px-5 py-2.5" style={{ paddingLeft: `${20 + depth * 22}px` }}>
                        <div className="flex items-center gap-1.5">
                          {node.children.length ? (
                            <button onClick={() => toggle(node.id)} aria-expanded={expanded.has(node.id)} aria-label={`${expanded.has(node.id) ? "Collapse" : "Expand"} ${node.label}`} className="rounded p-0.5 text-gray-400 hover:bg-surface-subtle hover:text-gray-700">
                              <IconChevronRight className={`h-4 w-4 transition-transform ${expanded.has(node.id) ? "rotate-90" : ""}`} aria-hidden="true" />
                            </button>
                          ) : <span className="inline-block w-5" />}
                          <span className={depth === 0 ? "font-semibold text-gray-900" : "text-gray-700"}>{node.label}</span>
                          <span className="text-[11px] text-gray-400">{LEVEL_LABEL[node.level as TreeLevel].toLowerCase()}</span>
                        </div>
                      </td>
                      <td className="px-3 py-2.5 text-right font-semibold tabular-nums">{node.stores}</td>
                      <td className="px-3 py-2.5 text-right tabular-nums">{node.vendors}</td>
                      <td className={`px-3 py-2.5 text-right tabular-nums ${node.behind ? "text-status-warning" : "text-gray-400"}`}>{node.behind}</td>
                      <td className="px-3 py-2.5 text-right tabular-nums">{node.markedToday}</td>
                      <td className="px-3 py-2.5 text-right tabular-nums">{node.bottles.toLocaleString("en-IN")}</td>
                      <td className="px-5 py-2.5 text-right">
                        {canPick && !picked && <button onClick={() => onPick(node.path)} className="text-xs font-semibold text-brand-600 hover:text-brand-700">Filter</button>}
                        {picked && <span className="text-xs font-semibold text-gray-500">Selected</span>}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
              <tfoot className="sticky bottom-0 bg-brand-50 font-bold text-gray-900">
                <tr className="border-t border-surface-border">
                  <td className="px-5 py-3">All {name || "live stores"}</td>
                  <td className="px-3 py-3 text-right tabular-nums">{totals.stores}</td>
                  <td className="px-3 py-3 text-right tabular-nums">{totals.vendors}</td>
                  <td className="px-3 py-3 text-right tabular-nums">{totals.behind}</td>
                  <td className="px-3 py-3 text-right tabular-nums">{totals.markedToday}</td>
                  <td className="px-3 py-3 text-right tabular-nums">{totals.bottles.toLocaleString("en-IN")}</td>
                  <td />
                </tr>
              </tfoot>
            </table>
          </div>
        </>
      )}
    </section>
  );
}
