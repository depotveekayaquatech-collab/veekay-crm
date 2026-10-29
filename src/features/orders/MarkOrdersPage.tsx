import { distinctOptions } from "@/lib/options";
import { useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { usePersistentState } from "@/hooks/usePersistentState";
import { usePermission } from "@/hooks/usePermission";
import { useAuth } from "@/features/auth/useAuth";
import { Select } from "@/components/ui/Select";
import { Skeleton } from "@/components/feedback/Skeleton";
import { EmptyState } from "@/components/feedback/EmptyState";
import { ErrorState } from "@/components/feedback/ErrorState";
import { Button } from "@/components/ui/Button";
import { CappingAlertBanner } from "@/features/capping/CappingAlertBanner";
import { MultiDateMarkModal } from "@/features/orders/MultiDateMarkModal";
import { OrderCalendar } from "@/features/orders/OrderCalendar";
import { QuickEntry } from "@/features/orders/QuickEntry";
import { StoreSummary } from "@/features/orders/StoreSummary";
import { RegionFilter, SegmentedControl, SelectStorePrompt, StorePicker } from "@/features/orders/ui";
import { useCalendar, useCorrectOwnEntry, useMarkManyOrders, useMarkOrder, useMyStores } from "@/features/orders/useOrders";

export function MarkOrdersPage() {
  const { data: stores, isLoading, isError, refetch } = useMyStores();
  const [vendor, setVendor] = useState("");
  const [pickedPartner, setPartner] = usePersistentState<string>("orders.platform", "");
  const [region, setRegion] = useState("");
  const [params] = useSearchParams();
  const canMark = usePermission("orders.mark");
  const isAdmin = usePermission("orders.correct");
  const { user } = useAuth();
  const [pickedId, setStoreId] = useState(params.get("store") ?? "");
  // Someone with a single store has nothing to pick — open it straight away.
  const storeId = pickedId || (stores?.length === 1 ? stores[0].id : "");
  // A link from Performance names the month of the day to mark ("?store=…&month=2026-10"): the calendar opens there.
  const [period, setPeriod] = useState<{ year?: number; month?: number }>(() => {
    const m = /^(\d{4})-(\d{2})$/.exec(params.get("month") ?? "");
    return m && params.get("store") ? { year: Number(m[1]), month: Number(m[2]) } : {};
  });
  const [savedView, setView] = usePersistentState<"quick" | "store">("orders.view", "quick");
  // The first days of a month: last month stays open (to mark, to check, and to change with the permission). A tab switches the whole page to it.
  const [mode, setMode] = useState<"this" | "last">("this");
  const [missingOnly, setMissingOnly] = useState(false);
  const openUntil = stores?.find((s) => s.lastMonthOpenUntil)?.lastMonthOpenUntil ?? null;
  const prevMonth = useMemo(() => {
    const t = stores?.[0]?.today;
    if (!t) return null;
    const d = new Date(`${t.slice(0, 7)}-01T12:00:00`);
    d.setMonth(d.getMonth() - 1);
    return { year: d.getFullYear(), month: d.getMonth() + 1, label: d.toLocaleDateString("en-IN", { month: "long", year: "numeric" }) };
  }, [stores]);
  const lastMode = mode === "last" && Boolean(openUntil) && Boolean(prevMonth);
  const view = lastMode ? "store" : params.get("store") || !canMark ? "store" : savedView;
  const mark = useMarkOrder();
  const correctOwn = useCorrectOwnEntry();
  const markMany = useMarkManyOrders();
  const [multiModalOpen, setMultiModalOpen] = useState(false);
  const { data: calendar, isLoading: calLoading, isError: calError, refetch: refetchCal } = useCalendar(
    storeId || null,
    period.year,
    period.month,
  );

  const partners = useMemo(
    () => distinctOptions(stores ?? [], (s) => (s.partnerSlug ? { value: s.partnerSlug, label: s.partnerName ?? s.partnerSlug } : null)),
    [stores],
  );
  // Platforms are kept apart: one is always selected (the first, unless the user picks another).
  const partner = partners.some((p) => p.value === pickedPartner) ? pickedPartner : (partners[0]?.value ?? "");

  const ofPartner = useMemo(() => (stores ?? []).filter((s) => !partner || s.partnerSlug === partner), [stores, partner]);
  const regions = useMemo(
    () => distinctOptions(ofPartner, (s) => (s.regionId ? { value: s.regionId, label: s.regionName ?? "Region" } : null)),
    [ofPartner],
  );
  const vendors = useMemo(() => distinctOptions(ofPartner, (s) => (s.vendorName ? { value: s.vendorName.toLowerCase(), label: s.vendorName } : null)), [ofPartner]);

  const filtered = useMemo(
    () =>
      ofPartner.filter(
        (s) =>
          (!region || s.regionId === region) && (!vendor || (s.vendorName ?? "").toLowerCase() === vendor) && !(lastMode && missingOnly && s.lastMonthMissing === 0),
      ),
    [ofPartner, region, vendor, lastMode, missingOnly],
  );

  const selectedStore = stores?.find((s) => s.id === storeId) ?? null;

  function choose(id: string) {
    setStoreId(id);
    setPeriod(lastMode && prevMonth ? { year: prevMonth.year, month: prevMonth.month } : {});
  }

  function switchMode(next: "this" | "last") {
    setMode(next);
    setPeriod(next === "last" && prevMonth ? { year: prevMonth.year, month: prevMonth.month } : {});
  }

  const storesMissing = (stores ?? []).filter((s) => s.lastMonthMissing > 0).length;

  return (
    <div className="flex flex-col gap-5">
      <CappingAlertBanner />
      <div className="flex flex-wrap items-center gap-3">
        {openUntil && prevMonth && (
          <SegmentedControl
            label="Month"
            value={lastMode ? "last" : "this"}
            onChange={(v) => switchMode(v as "this" | "last")}
            options={[
              { value: "this", label: "This month" },
              { value: "last", label: `Last month${storesMissing ? ` (${storesMissing})` : ""}` },
            ]}
          />
        )}
        {canMark && !lastMode && <SegmentedControl
          label="View"
          value={view}
          onChange={setView}
          options={[
            { value: "quick", label: "Quick entry" },
            { value: "store", label: "By store" },
          ]}
        />}
        {partners.length > 1 && (
          <SegmentedControl
            label="Platform"
            value={partner}
            onChange={(v) => {
              setPartner(v);
              setRegion("");
              setVendor("");
              setStoreId("");
            }}
            options={partners}
          />
        )}
        {partners.length === 1 && (
          <span className="rounded-full bg-brand-50 px-3 py-1.5 text-xs font-bold text-brand-700">{partners[0].label}</span>
        )}
        {regions.length > 1 && <RegionFilter value={region} onChange={(v) => { setRegion(v); setStoreId(""); }} options={regions} className="sm:w-48 [&_label]:sr-only" />}
        {vendors.length > 1 && (
          <div className="w-full sm:w-48 [&_label]:sr-only">
            <Select label="Vendor" value={vendor} onChange={(e) => setVendor(e.target.value)} placeholder="All vendors" options={vendors} />
          </div>
        )}
        {canMark && (
          <Button
            type="button"
            variant="secondary"
            onClick={() => setMultiModalOpen(true)}
            className="sm:ml-auto flex items-center gap-1.5 font-bold"
          >
            <span>⚡</span>
            <span>Mark multiple dates</span>
          </Button>
        )}
      </div>

      {lastMode && prevMonth && openUntil && (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-status-warning/30 bg-status-warning-soft/60 px-4 py-3 text-sm">
          <p className="text-gray-800">
            <b>{prevMonth.label}</b> is open until <b>{new Date(`${openUntil}T00:00:00`).toLocaleDateString("en-IN", { day: "numeric", month: "short" })}</b>. Pick a store to check or mark its days.
            {" "}{storesMissing > 0 ? `${storesMissing} of your stores still have days with no entry.` : "Every store has all its days."}
            {user?.canEditPrevious ? " You can change any day; every change is kept in the history." : ""} After that only an admin can change it.
          </p>
          <label className="flex items-center gap-2 text-xs font-semibold text-gray-700">
            <input type="checkbox" checked={missingOnly} onChange={(e) => setMissingOnly(e.target.checked)} />
            Only stores with days missing
          </label>
        </div>
      )}

      {isLoading && (
        <div className="grid gap-5 lg:grid-cols-[21rem_1fr]">
          <Skeleton className="h-96" />
          <Skeleton className="h-96" />
        </div>
      )}
      {isError && <ErrorState message="Couldn't load your stores." onRetry={() => refetch()} />}

      {stores && stores.length === 0 && (
        <EmptyState title="No stores assigned yet" description={canMark ? "An admin needs to assign you a region or states." : "There are no live stores on your platform yet."} />
      )}

      {stores && stores.length > 0 && canMark && view === "quick" && <QuickEntry stores={filtered} />}

      {stores && stores.length > 0 && (view === "store" || !canMark) && (
        <div className="grid items-start gap-5 lg:grid-cols-[21rem_1fr]">
          <StorePicker
            title={canMark ? "Your stores" : "Stores"}
            stores={filtered}
            selectedId={storeId}
            onSelect={choose}
          />

          <div className="flex min-w-0 flex-col gap-5">
            {!selectedStore && <SelectStorePrompt text={canMark ? "Pick one of your stores to log its daily bottle count." : "Pick a store to see its daily entries."} />}
            {selectedStore && (
              <>
                <StoreSummary store={selectedStore} />
                {calError ? (
                  <ErrorState message="Couldn't load this store's calendar." onRetry={() => refetchCal()} />
                ) : calLoading || !calendar ? (
                  <Skeleton className="h-96" />
                ) : (
                  <>
                  {!calendar.canMark && !isAdmin && (
                    <p role="status" className="mb-3 rounded-lg bg-surface-subtle px-3.5 py-2.5 text-sm text-gray-700">
                      {calendar.monthLabel} is closed for entries. You can see what was entered, but only an admin can add or change entries now.
                    </p>
                  )}
                  <OrderCalendar
                    calendar={calendar}
                    marking={mark.isPending || markMany.isPending || correctOwn.isPending}
                    onNavigate={(year, month) => setPeriod({ year, month })}
                    onMark={canMark && (isAdmin || calendar.canMark) ? (date, count) => mark.mutateAsync({ storeId: selectedStore.id, date, count }) : undefined}
                    correctAny={Boolean(user?.canEditPrevious)}
                    onCorrect={canMark && !isAdmin && calendar.canMark && (user?.canCorrectOwnEntries || user?.canEditPrevious) ? (date, count) => correctOwn.mutateAsync({ storeId: selectedStore.id, date, count }) : undefined}
                    onMarkMany={canMark && (isAdmin || calendar.canMark) ? (entries) => markMany.mutateAsync({ storeId: selectedStore.id, entries }) : undefined}
                    isAdmin={isAdmin}
                  />
                  </>
                )}
              </>
            )}
          </div>
        </div>
      )}

      {canMark && (
        <MultiDateMarkModal
          isOpen={multiModalOpen}
          onClose={() => setMultiModalOpen(false)}
          stores={filtered}
          initialStoreId={storeId}
          isAdmin={isAdmin}
        />
      )}
    </div>
  );
}
