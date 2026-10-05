import { useState } from "react";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { IconDownload, IconReport } from "@/components/ui/icons";
import { SegmentedControl } from "@/features/orders/ui";
import { useAuth } from "@/features/auth/useAuth";
import { daysAgo, isoDate } from "@/lib/dates";
import { pushToast } from "@/lib/toast";
import { apiBlob } from "@/services/api";

type Preset = "7" | "30" | "month" | "last-month" | "custom";

const MAX_DAYS = 62;

function rangeFor(preset: Exclude<Preset, "custom">): { from: string; to: string } {
  const now = new Date();
  if (preset === "7") return { from: daysAgo(6), to: daysAgo(0) };
  if (preset === "30") return { from: daysAgo(29), to: daysAgo(0) };
  if (preset === "month") return { from: isoDate(new Date(now.getFullYear(), now.getMonth(), 1)), to: daysAgo(0) };
  return {
    from: isoDate(new Date(now.getFullYear(), now.getMonth() - 1, 1)),
    to: isoDate(new Date(now.getFullYear(), now.getMonth(), 0)),
  };
}

function dayCount(from: string, to: string): number {
  return Math.round((new Date(`${to}T12:00:00`).getTime() - new Date(`${from}T12:00:00`).getTime()) / 86_400_000) + 1;
}

/** Delivery report for a partner account: pick a period, download the Excel. Nothing is previewed on screen. */
export function PartnerDeliveryReport() {
  const { user } = useAuth();
  const [preset, setPreset] = useState<Preset>("7");
  const [custom, setCustom] = useState(rangeFor("7"));
  const [busy, setBusy] = useState(false);

  const { from, to } = preset === "custom" ? custom : rangeFor(preset);
  const days = dayCount(from, to);
  const problem =
    to < from ? "The end date is before the start date." : days > MAX_DAYS ? `Choose at most ${MAX_DAYS} days at a time.` : to > daysAgo(0) ? "The end date can't be in the future." : null;

  async function download() {
    setBusy(true);
    try {
      const blob = await apiBlob(`/partner/delivery-report?start=${from}&end=${to}`);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `delivery-report-${from}_${to}.xlsx`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 30_000);
      pushToast("Delivery report downloaded.", "success");
    } catch {
      /* the API layer already showed the reason */
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <PageHeader title="Delivery reports" subtitle="Bottles delivered to each of your stores, day by day — download as an Excel sheet." />

      <section className="max-w-2xl rounded-xl border border-surface-border bg-surface p-5 shadow-card sm:p-7">
        <div className="flex items-start gap-4">
          <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-aqua-50 text-aqua-600">
            <IconReport className="h-6 w-6" />
          </span>
          <div>
            <h3 className="text-base font-bold text-heading">Daily distribution{user?.fullName ? ` · ${user.fullName}` : ""}</h3>
            <p className="mt-0.5 text-sm text-gray-500">
              One row per store, one column per day. A blank cell means no number was recorded that day. The sheet has no totals.
            </p>
          </div>
        </div>

        <div className="mt-6 flex flex-col gap-4">
          <div>
            <p className="mb-1.5 text-sm font-medium text-gray-700">Period</p>
            <SegmentedControl
              label="Period"
              value={preset}
              onChange={(v) => {
                if (v === "custom") setCustom({ from, to });
                setPreset(v);
              }}
              options={[
                { value: "7", label: "Last 7 days" },
                { value: "30", label: "Last 30 days" },
                { value: "month", label: "This month" },
                { value: "last-month", label: "Last month" },
                { value: "custom", label: "Custom" },
              ]}
            />
          </div>

          {preset === "custom" && (
            <div className="grid max-w-md grid-cols-2 gap-3">
              <Input label="From" type="date" value={custom.from} max={daysAgo(0)} onChange={(e) => setCustom((c) => ({ ...c, from: e.target.value }))} />
              <Input label="To" type="date" value={custom.to} max={daysAgo(0)} onChange={(e) => setCustom((c) => ({ ...c, to: e.target.value }))} />
            </div>
          )}

          <p className="text-sm text-gray-600">
            {problem ? <span className="text-status-danger">{problem}</span> : <>Covers <b>{from}</b> to <b>{to}</b> · {days} day{days === 1 ? "" : "s"}.</>}
          </p>

          <div>
            <Button size="lg" onClick={() => void download()} isLoading={busy} disabled={Boolean(problem)}>
              <IconDownload className="h-4 w-4" />
              Download Excel
            </Button>
          </div>
        </div>
      </section>
    </div>
  );
}
