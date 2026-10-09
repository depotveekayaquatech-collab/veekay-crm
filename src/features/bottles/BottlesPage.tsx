import { useState } from "react";
import { PageHeader } from "@/components/layout/PageHeader";
import { SegmentedControl } from "@/features/orders/ui";
import { DeleteCodes } from "@/features/bottles/DeleteCodes";
import { BottleList } from "@/features/bottles/BottleList";
import { PrintCodes } from "@/features/bottles/PrintCodes";
import { ScanPanel } from "@/features/bottles/ScanPanel";
import { usePermission } from "@/hooks/usePermission";

type Tab = "list" | "scan" | "print" | "delete";

export function BottlesPage() {
  const canDelete = usePermission("bottles.delete");
  const canView = usePermission("bottles.view") || canDelete;
  const canScan = usePermission("bottles.scan");
  const canManage = usePermission("bottles.manage");
  const tabs: { value: Tab; label: string }[] = [
    ...(canView ? [{ value: "list" as const, label: "Overview" }] : []),
    ...(canScan ? [{ value: "scan" as const, label: "Scan" }] : []),
    ...(canManage ? [{ value: "print" as const, label: "Print codes" }] : []),
    ...(canDelete ? [{ value: "delete" as const, label: "Delete codes" }] : []),
  ];
  const [tab, setTab] = useState<Tab>(tabs[0]?.value ?? "list");
  const current = tabs.some((t) => t.value === tab) ? tab : tabs[0]?.value;

  return (
    <div className="flex flex-col gap-5">
      <PageHeader title="Bottle tracking" subtitle="Every bottle has its own QR code: scan it IN when it reaches a store and OUT when it leaves." />
      {tabs.length > 1 && <div className="max-w-full self-start"><SegmentedControl label="Bottle tracking" value={current ?? "list"} onChange={setTab} options={tabs} /></div>}
      {current === "list" && <BottleList canManage={canManage} />}
      {current === "scan" && <ScanPanel />}
      {current === "print" && <PrintCodes />}
      {current === "delete" && <DeleteCodes />}
    </div>
  );
}
