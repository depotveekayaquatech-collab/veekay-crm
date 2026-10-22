import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Skeleton } from "@/components/feedback/Skeleton";
import { ErrorState } from "@/components/feedback/ErrorState";
import { MergeStoresModal } from "@/features/stores/MergeStoresModal";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { pushToast } from "@/lib/toast";
import {
  listDuplicateStores, listImportIssues, listPlatformCheck, moveStoreToPlatform,
  type DuplicateGroup, type ImportIssueRun, type MergePairInput, type PlatformCheckRow,
} from "@/services/stores";
import type { Store } from "@/types/store";

export const DUPLICATES_KEY = ["duplicate-stores"];
export const IMPORT_ISSUES_KEY = ["store-import-issues"];
export const PLATFORM_CHECK_KEY = ["store-platform-check"];

export function useDuplicateStores() {
  return useQuery({ queryKey: DUPLICATES_KEY, queryFn: listDuplicateStores, staleTime: 60_000 });
}

export function usePlatformCheck() {
  return useQuery({ queryKey: PLATFORM_CHECK_KEY, queryFn: listPlatformCheck, staleTime: 60_000 });
}

export function useImportIssues() {
  return useQuery({ queryKey: IMPORT_ISSUES_KEY, queryFn: listImportIssues, staleTime: 60_000 });
}

const groupKey = (g: DuplicateGroup) => `${g.kind}|${g.platform}|${g.label}`;
const day = (iso: string) => new Date(iso).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
const when = (iso: string) => new Date(iso).toLocaleString(undefined, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });

const REASON: Record<string, { title: string; tone: "warning" | "danger" | "neutral" }> = {
  name_matches_several_stores: { title: "Name already on several stores", tone: "danger" },
  name_repeated_in_sheet: { title: "Name repeated in the sheet", tone: "warning" },
  missing_name_or_id: { title: "Missing name or Outlet ID", tone: "danger" },
  id_too_long: { title: "Outlet ID too long", tone: "danger" },
  status_not_understood: { title: "Status not understood", tone: "warning" },
};

/**
 * Everything that needs sorting after a store upload, in one place:
 *   1. stores that exist more than once (same name on a platform, or the same Outlet ID) - fix an Outlet ID (Edit) or merge the extra
 *      copies into the one to keep; a merge moves every order, document and ticket across first, so nothing is lost;
 *   2. the rows of the latest upload that could not be used (a repeated name, a name with no ID, a status that is not understood).
 */
export function DuplicateStores({ onEdit, canMerge }: { onEdit: (s: Store) => void; canMerge: boolean }) {
  const { data, isLoading, isError, refetch } = useDuplicateStores();
  const issues = useImportIssues();
  const [keep, setKeep] = useState<Record<string, string>>({});
  const [merging, setMerging] = useState<{ platform: string; pairs: MergePairInput[] } | null>(null);

  if (isLoading) return <Skeleton className="h-64" />;
  if (isError || !data) return <ErrorState message="Couldn't load the duplicate stores." onRetry={() => refetch()} />;
  const runs = (issues.data?.runs ?? []).filter((r) => r.issueCount > 0);

  return (
    <div className="flex flex-col gap-6">
      <section className="flex flex-col gap-4">
        <h2 className="text-sm font-bold uppercase tracking-wider text-gray-500">Stores that exist more than once</h2>
        {data.groups.length === 0 ? (
          <div className="rounded-2xl border border-dashed border-surface-border bg-surface p-8 text-center text-sm text-gray-500">
            No duplicate stores. Every store has its own name and Outlet ID.
          </div>
        ) : (
          <p className="rounded-xl bg-status-warning-soft/60 px-4 py-3 text-sm text-gray-700">
            <b>{data.totalGroups}</b> group{data.totalGroups === 1 ? "" : "s"} covering <b>{data.totalStores}</b> stores. Use <b>Edit</b> to correct a
            store's Outlet ID. {canMerge ? "Use Merge to fold the extra copies into the store you keep; all their orders and documents move with them." : ""}
          </p>
        )}
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
                      <span className="block truncate font-medium text-gray-900">{s.store.externalCode} <span className="text-xs font-normal text-gray-400">· {s.store.crmCode}</span></span>
                      <span className="block truncate text-xs text-gray-500">
                        {s.store.name} · added {day(s.createdAt)}
                        {s.store.city ? ` · ${s.store.city}` : ""}
                        {s.store.vendorName ? ` · vendor ${s.store.vendorName}` : ""}
                        {s.store.pocName ? ` · POC ${s.store.pocName}` : ""}
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
      </section>

      <section className="flex flex-col gap-4">
        <h2 className="text-sm font-bold uppercase tracking-wider text-gray-500">Rows the last upload could not use</h2>
        {issues.isLoading ? (
          <Skeleton className="h-24" />
        ) : runs.length === 0 ? (
          <div className="rounded-2xl border border-dashed border-surface-border bg-surface p-8 text-center text-sm text-gray-500">
            The latest store upload had no rows that needed attention.
          </div>
        ) : (
          runs.map((r) => <IssueRun key={r.platformSlug} run={r} />)
        )}
      </section>

      <PlatformCheck canMove={canMerge} />

      {merging && <MergeStoresModal onClose={() => setMerging(null)} initial={merging} />}
    </div>
  );
}

const slugOf = (name: string | null) => ((name ?? "").toLowerCase().includes("zepto") ? "zepto" : "blinkit");

/** Stores that look filed under the wrong platform (that is how one platform's capping or entries can show up on the other's stores). */
function PlatformCheck({ canMove }: { canMove: boolean }) {
  const q = usePlatformCheck();
  const qc = useQueryClient();
  const move = useMutation({
    mutationFn: ({ id, to }: { id: string; to: string }) => moveStoreToPlatform(id, to),
    onSuccess: (r) => {
      for (const k of [PLATFORM_CHECK_KEY, DUPLICATES_KEY, ["stores"], ["capping"], ["pending"], ["order-insights"], ["inventory"]]) qc.invalidateQueries({ queryKey: k });
      pushToast(`${r.name} moved to ${r.platform}${r.cappingRemoved ? " (its Zepto capping number was removed)" : ""}.`, "success");
    },
    onError: (e) => pushToast(e instanceof Error ? e.message : "Could not move the store.", "error"),
  });

  const ask = (row: PlatformCheckRow, to: string) => {
    const label = to === "zepto" ? "Zepto" : "Blinkit";
    const extra = row.hasCapping && to !== "zepto" ? " Its Zepto capping number will be removed." : "";
    if (window.confirm(`Move ${row.store.name} (${row.store.externalCode}) from ${row.platform} to ${label}? Its ${row.orderDays} order day${row.orderDays === 1 ? "" : "s"} and documents go with it.${extra}`)) {
      move.mutate({ id: row.store.id, to });
    }
  };

  return (
    <section className="flex flex-col gap-4">
      <h2 className="text-sm font-bold uppercase tracking-wider text-gray-500">Possibly on the wrong platform</h2>
      {q.isLoading ? (
        <Skeleton className="h-24" />
      ) : q.isError || !q.data ? (
        <ErrorState message="Couldn't run the platform check." onRetry={() => q.refetch()} />
      ) : q.data.stores.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-surface-border bg-surface p-8 text-center text-sm text-gray-500">
          Every store looks filed under the right platform.
        </div>
      ) : (
        <>
          <p className="rounded-xl bg-status-warning-soft/60 px-4 py-3 text-sm text-gray-700">
            <b>{q.data.total}</b> store{q.data.total === 1 ? "" : "s"} look like they belong to the other platform. Check each one before moving it: the
            reason is shown. A move keeps all its orders and documents, and a Zepto capping number is dropped when a store leaves Zepto.
          </p>
          <section className="overflow-hidden rounded-2xl border border-surface-border bg-surface shadow-card">
            <ul className="divide-y divide-surface-border text-sm">
              {q.data.stores.map((r) => {
                const to = r.suggestedPlatform ?? (slugOf(r.platform) === "zepto" ? "blinkit" : "zepto");
                return (
                  <li key={r.store.id} className="flex flex-wrap items-center gap-3 px-4 py-2.5">
                    <span className="min-w-0 flex-1">
                      <span className="block truncate font-medium text-gray-900">{r.store.name}</span>
                      <span className="block truncate text-xs text-gray-500">
                        {r.store.crmCode} · {r.store.externalCode} · on <b>{r.platform}</b> · {r.store.status} · {r.orderDays} order day{r.orderDays === 1 ? "" : "s"}
                        {r.hasCapping ? " · has a capping number" : ""}
                      </span>
                      <span className="block text-xs text-status-danger">{r.reasons.join(" · ")}</span>
                    </span>
                    {canMove && (
                      <Button size="sm" variant="secondary" isLoading={move.isPending && move.variables?.id === r.store.id} onClick={() => ask(r, to)}>
                        Move to {to === "zepto" ? "Zepto" : "Blinkit"}
                      </Button>
                    )}
                  </li>
                );
              })}
            </ul>
          </section>
        </>
      )}
    </section>
  );
}

function IssueRun({ run }: { run: ImportIssueRun }) {
  return (
    <section className="overflow-hidden rounded-2xl border border-surface-border bg-surface shadow-card">
      <header className="border-b border-surface-border bg-surface-subtle px-4 py-3">
        <p className="text-sm font-semibold text-gray-900">{run.platform}</p>
        <p className="text-xs text-gray-500">
          Upload of {when(run.at)} · {run.rowsRead ?? "?"} rows read · {run.created ?? 0} added · {run.updated ?? 0} updated ·{" "}
          <b>{run.issueCount}</b> row{run.issueCount === 1 ? "" : "s"} need attention
          {run.issueCount > run.issues.length ? ` (showing the first ${run.issues.length})` : ""}
        </p>
      </header>
      <ul className="divide-y divide-surface-border text-sm">
        {run.issues.map((i, n) => {
          const r = REASON[i.reason] ?? { title: i.reason, tone: "neutral" as const };
          return (
            <li key={`${i.row}-${n}`} className="flex flex-col gap-1 px-4 py-2.5">
              <div className="flex flex-wrap items-center gap-2">
                <Badge tone={r.tone}>{r.title}</Badge>
                <span className="text-xs text-gray-500">sheet row {i.row}</span>
                <span className="min-w-0 truncate font-medium text-gray-900">{i.name ?? "(no name)"}</span>
                {i.code ? <span className="text-xs text-gray-500">· {i.code}</span> : null}
              </div>
              <p className="text-xs text-gray-600">{i.detail}</p>
              {i.crmStores.length > 0 && (
                <p className="text-xs text-gray-500">
                  In the CRM under this name: {i.crmStores.map((c) => `${c.externalCode} (${c.status})`).join(", ")}
                </p>
              )}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
