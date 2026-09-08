import { IconInfo } from "@/components/ui/icons";

export function DemoDataBanner() {
  return (
    <div className="flex items-start gap-2.5 rounded-md border border-status-warning/25 bg-status-warning-soft px-3.5 py-2.5 text-sm text-status-warning">
      <IconInfo className="mt-0.5 h-4 w-4 shrink-0" />
      <span>Showing demo data — the live endpoint isn't connected yet.</span>
    </div>
  );
}
