import { useState } from "react";
import { Link } from "react-router-dom";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/Button";
import { AdminCsvTab } from "@/features/vendorpay/AdminCsvTab";
import { AdminKeyTab } from "@/features/vendorpay/AdminKeyTab";
import { AdminLogsTab } from "@/features/vendorpay/AdminLogsTab";
import { AdminUnmatchedTab } from "@/features/vendorpay/AdminUnmatchedTab";
import { AdminVendorsTab } from "@/features/vendorpay/AdminVendorsTab";
import { useUnmatched } from "@/features/vendorpay/adminApi";
import { useFreshness } from "@/features/vendorpay/api";
import { FreshnessBanner } from "@/features/vendorpay/parts";
import { SegmentedControl } from "@/features/orders/ui";

type Tab = "csv" | "logs" | "unmatched" | "vendors" | "key";

/** Administrators only (the API checks vendorpay.manage on every call here). */
export function VendorPaymentsAdminPage() {
  const [tab, setTab] = useState<Tab>("csv");
  const { data: freshness } = useFreshness();
  const { data: unmatched } = useUnmatched();
  const waiting = unmatched?.reduce((sum, g) => sum + g.rows, 0) ?? 0;

  return (
    <div className="flex flex-col gap-5">
      <PageHeader
        title="Vendor payments: manage"
        subtitle="Upload from Busy by hand, see every sync, sort out unknown vendor codes and look after the vendor list."
        action={
          <Link to="/vendor-payments">
            <Button variant="secondary">Back to the employee view</Button>
          </Link>
        }
      />
      <FreshnessBanner freshness={freshness} canManage={false} />
      <SegmentedControl<Tab>
        label="Vendor payments admin"
        value={tab}
        onChange={setTab}
        options={[
          { value: "csv", label: "Upload CSV" },
          { value: "logs", label: "Sync history" },
          { value: "unmatched", label: waiting ? `Unmatched codes (${waiting})` : "Unmatched codes" },
          { value: "vendors", label: "Vendors" },
          { value: "key", label: "Connection and key" },
        ]}
      />
      {tab === "csv" && <AdminCsvTab />}
      {tab === "logs" && <AdminLogsTab />}
      {tab === "unmatched" && <AdminUnmatchedTab />}
      {tab === "vendors" && <AdminVendorsTab />}
      {tab === "key" && <AdminKeyTab />}
    </div>
  );
}
