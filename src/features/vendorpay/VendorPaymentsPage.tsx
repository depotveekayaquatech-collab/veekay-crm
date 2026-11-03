import { useMemo } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/Button";
import { Select } from "@/components/ui/Select";
import { useVendorChoices, useFreshness, type SortDirection, type SortKey } from "@/features/vendorpay/api";
import { AllVendorsView } from "@/features/vendorpay/AllVendorsView";
import { currentMonthIst, isMonth, monthOptions, vendorLabel } from "@/features/vendorpay/format";
import { FreshnessBanner } from "@/features/vendorpay/parts";
import { VendorView } from "@/features/vendorpay/VendorView";
import { usePermission } from "@/hooks/usePermission";

const SORTS: SortKey[] = ["name", "city", "code", "month_total", "paid", "pending", "closing"];
const isSort = (v: string | null): v is SortKey => SORTS.includes(v as SortKey);
const FIRST_PAGE = 1;

/** Read-only vendor totals, payments and balances for any staff member. The vendor, month, sort and page live in the address, so a view can be shared. */
export function VendorPaymentsPage() {
  const canManage = usePermission("vendorpay.manage");
  const [params, setParams] = useSearchParams();
  const { data: freshness } = useFreshness();
  const { data: vendors, isLoading: loadingVendors } = useVendorChoices();

  const current = currentMonthIst();
  const month = isMonth(params.get("month")) ? params.get("month")! : current;
  const vendor = params.get("vendor") ?? "";
  const sortParam = params.get("sort");
  const sort: SortKey = isSort(sortParam) ? sortParam : "name";
  const direction: SortDirection = params.get("dir") === "desc" ? "desc" : "asc";
  const page = Math.max(FIRST_PAGE, Number(params.get("page")) || FIRST_PAGE);

  function update(patch: Record<string, string | null>) {
    setParams((old) => {
      const next = new URLSearchParams(old);
      for (const [key, value] of Object.entries(patch)) {
        if (value) next.set(key, value);
        else next.delete(key);
      }
      return next;
    }, { replace: true });
  }

  const vendorOptions = useMemo(() => (vendors ?? []).map((v) => ({ value: v.vendorCode, label: vendorLabel(v) })), [vendors]);
  const months = useMemo(() => monthOptions(current, month), [current, month]);

  function sortBy(key: SortKey) {
    const nextDirection = key === sort && direction === "asc" ? "desc" : "asc";
    update({ sort: key === "name" ? null : key, dir: nextDirection === "desc" ? "desc" : null, page: null });
  }

  return (
    <div className="flex flex-col gap-5">
      <PageHeader
        title="Vendor payments"
        subtitle="What each vendor has billed, what has been paid and what is left, taken from the accounts in Busy. View only."
        action={
          canManage ? (
            <Link to="/vendor-payments/admin">
              <Button variant="secondary">Manage</Button>
            </Link>
          ) : undefined
        }
      />
      <FreshnessBanner freshness={freshness} canManage={canManage} />

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
        <Select
          label="Vendor"
          value={vendor}
          options={vendorOptions}
          placeholder="All vendors"
          searchable
          disabled={loadingVendors}
          onChange={(e) => update({ vendor: e.target.value || null, page: null })}
        />
        <Select label="Month" value={month} options={months} onChange={(e) => update({ month: e.target.value === current ? null : e.target.value })} />
      </div>

      {vendor ? (
        <VendorView vendorCode={vendor} month={month} onMonth={(m) => update({ month: m === current ? null : m })} />
      ) : (
        <AllVendorsView
          month={month}
          sort={sort}
          direction={direction}
          page={page}
          onSort={sortBy}
          onPage={(p) => update({ page: p === FIRST_PAGE ? null : String(p) })}
          onOpenVendor={(code) => update({ vendor: code, page: null })}
        />
      )}
    </div>
  );
}
