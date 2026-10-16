import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { SelectField } from "@/components/ui/Dropdown";
import { IconDownload } from "@/components/ui/icons";
import { usePartners } from "@/features/stores/useStores";
import { VendorRatesPanel } from "@/features/reports/VendorRatesPanel";
import { daysAgo } from "@/lib/dates";
import { pushToast } from "@/lib/toast";
import { apiBlob } from "@/services/api";

const input =
  "h-10 w-full rounded-lg border border-surface-border bg-surface px-3 text-sm shadow-sm outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20";

/** Date-wise delivery sheet WITH the vendor rate and amount (admins only). The normal report is unchanged. */
function RateReportDownload() {
  const { data: partners = [] } = usePartners();
  const [from, setFrom] = useState(daysAgo(6));
  const [to, setTo] = useState(daysAgo(0));
  const [partner, setPartner] = useState("blinkit");
  const [state, setState] = useState("");
  const [city, setCity] = useState("");
  const [busy, setBusy] = useState(false);
  const bad = from > to;

  async function download() {
    if (bad) return;
    setBusy(true);
    try {
      const p = new URLSearchParams({ start: from, end: to, include_rate: "true" });
      if (partner) p.set("partner", partner);
      if (state.trim()) p.set("state", state.trim());
      if (city.trim()) p.set("city", city.trim());
      const blob = await apiBlob(`/orders/matrix/export?${p.toString()}`);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `daily-distribution-with-rate-${from}_${to}.xlsx`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      pushToast("Excel downloaded.", "success");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="rounded-xl border border-surface-border bg-surface shadow-card">
      <header className="border-b border-surface-border/80 px-5 py-4">
        <h3 className="text-sm font-bold text-gray-900">Download delivery sheet with vendor rate</h3>
        <p className="mt-0.5 text-xs text-gray-500">
          The same date-wise sheet as Delivery Reports, plus <b>Vendor Rate</b> and <b>Amount</b> (bottles × the city&apos;s rate in force on the last date). Up to 62 days.
        </p>
      </header>
      <div className="flex flex-col gap-4 p-5">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
          <label className="flex flex-col gap-1.5 text-[13px] font-semibold text-gray-700">
            Date from
            <input type="date" className={input} value={from} max={to} onChange={(e) => setFrom(e.target.value)} />
          </label>
          <label className="flex flex-col gap-1.5 text-[13px] font-semibold text-gray-700">
            Date to
            <input type="date" className={input} value={to} min={from} onChange={(e) => setTo(e.target.value)} />
          </label>
          <label className="flex flex-col gap-1.5 text-[13px] font-semibold text-gray-700">
            Channel
            <SelectField className={input} value={partner} onChange={(e) => setPartner(e.target.value)}>
              {(partners.length ? partners : [{ slug: "blinkit", name: "Blinkit" }]).map((p) => (
                <option key={p.slug} value={p.slug}>{p.name}</option>
              ))}
            </SelectField>
          </label>
          <label className="flex flex-col gap-1.5 text-[13px] font-semibold text-gray-700">
            State
            <input className={input} value={state} onChange={(e) => setState(e.target.value)} placeholder="All states" />
          </label>
          <label className="flex flex-col gap-1.5 text-[13px] font-semibold text-gray-700">
            City
            <input className={input} value={city} onChange={(e) => setCity(e.target.value)} placeholder="All cities" />
          </label>
        </div>
        {bad && <p className="text-sm text-status-danger">“Date from” must not be after “Date to”.</p>}
        <div>
          <Button onClick={() => void download()} isLoading={busy} disabled={bad}>
            <IconDownload className="h-4 w-4" /> Download Excel with vendor rate
          </Button>
        </div>
      </div>
    </section>
  );
}

export function VendorRatesTab() {
  return (
    <div className="flex flex-col gap-6">
      <VendorRatesPanel />
      <RateReportDownload />
    </div>
  );
}
