import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Skeleton } from "@/components/feedback/Skeleton";
import { ErrorState } from "@/components/feedback/ErrorState";
import { MergeStoresModal } from "@/features/stores/MergeStoresModal";
import { listDuplicateStores, type DuplicateGroup, type MergePairInput } from "@/services/stores";
import type { Store } from "@/types/store";

export const DUPLICATES_KEY = ["duplicate-stores"];

export function useDuplicateStores() {
  return useQuery({ queryKey: DUPLICATES_KEY, queryFn: listDuplicateStores, staleTime: 60_000 });
}

const groupKey = (g: DuplicateGroup) => `${g.kind}|${g.platform}|${g.label}`;
const day = (iso: string) => new Date(iso).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });

/**
 * Stores that exist more than once. A store's name is its identity, so each group is something to fix: correct a store's
 * Outlet ID (Edit), or merge the extra copies into the one to keep (developer only). Merging moves every order, document and
 * ticket across first, so nothing is lost.
 */
export function DuplicateStores({ onEdit, canMerge }: { onEdit: (s: Store) => void; canMerge: boolean }) {
  const { data, isLoading, isError, refetch } = useDuplicateStores();
  const [keep, setKeep] = useState<Record<string, string>>({});
  const [merging, setMerging] = useState<{ platform: string; pairs: MergePairInput[] } | null>(null);

  if (isLoading) return <Skeleton className="h-64" />;
  if (isError || !data) return <ErrorState message="Couldn't load the duplicate stores." onRetry={() => refetch()} />;
  if (data.groups.length === 0) {
    return (
      <div className="rounded-2xl border border-dashed border-surface-border bg-surface p-10 text-center text-sm text-gray-500">
        No duplicate stores. Every store has its own name and Outlet ID.
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <p className="rounded-xl bg-status-warning-soft/60 px-4 py-3 text-sm text-gray-700">
        <b>{data.totalGroups}</b> group{data.totalGroups === 1 ? "" : "s"} covering <b>{data.totalStores}</b> stores. Use <b>Edit</b> to
        correct a store's Outlet ID. {canMerge ? "Use Merge to fold the extra copies into the store you keep; all their orders and documents move with them." : ""}
      </p>
      {data.groups.map((g) => {
        const key = groupKey(g);
        const keepId = keep[key] ?? g.stores[g.stores.length - 1].store.id;      // the newest one, which carries the real Outlet ID
        const kept = g.stores.find((s) => s.store.id === keepId) ?? g.stores[g.stores.length - 1];
        const others = g.stores.filter((s) => s.store.id !== kept.store.id);
        return (
          <section key={key} className="overflow-hidden rounded-2xl border border-surface-border bg-surface shadow-card">
            <header className="flex flex-wrap items-center justify-between gap-2 border-b border-surface-border bg-surface-subtle px-4 py-3">
              <div className="min-w-0">
                <p className="truncate text-sm font-semibold text-gray-900">{g.label}</p>
                <p className="text-xs text-gray-500">
                  {g.platform} · {g.kind === "name" ? "same store name" : "same Outlet ID (ignoring capitals, spaces and dashes)"} · {g.stores.length} stores
                </p>
              </div>
              {canMerge && (
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={() =>
                    setMerging({
                      platform: kept.store.partnerSlug ?? "",
                      pairs: others.map((o) => ({ oldCode: o.store.externalCode, newCode: kept.store.externalCode, oldId: o.store.id, newId: kept.store.id })),
                    })
                  }
                >
                  Merge {others.length} into the selected
                </Button>
              )}
            </header>
            <ul className="divide-y divide-surface-border text-sm">
              {g.stores.map((s) => (
                <li key={s.store.id} className="flex flex-wrap items-center gap-3 px-4 py-2.5">
                  {canMerge && (
                    <input
                      type="radio"
                      name={key}
                      aria-label={`Keep ${s.store.externalCode}`}
                      checked={s.store.id === kept.store.id}
                      onChange={() => setKeep((k) => ({ ...k, [key]: s.store.id }))}
                    />
                  )}
                  <span className="min-w-0 flex-1">
                    <span className="block truncate font-medium text-gray-900">{s.store.externalCode}</span>
                    <span className="block truncate text-xs text-gray-500">
                      {s.store.name} · added {day(s.createdAt)}
                      {s.store.city ? ` · ${s.store.city}` : ""}
                    </span>
                  </span>
                  <Badge tone={s.store.status === "LIVE" ? "success" : "neutral"}>{s.store.status}</Badge>
                  <span className="w-24 text-right text-xs tabular-nums text-gray-600">{s.orderDays} order day{s.orderDays === 1 ? "" : "s"}</span>
                  <Button size="sm" variant="secondary" onClick={() => onEdit(s.store)}>Edit</Button>
                </li>
              ))}
            </ul>
          </section>
        );
      })}
      {merging && <MergeStoresModal onClose={() => setMerging(null)} initial={merging} />}
    </div>
  );
}
