import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/Button";
import { SelectField } from "@/components/ui/Dropdown";
import { FileDropzone } from "@/components/ui/FileDropzone";
import { IconAlertTriangle, IconCheckCircle, IconDownload } from "@/components/ui/icons";
import { downloadCsv } from "@/lib/csv";
import { pushToast } from "@/lib/toast";
import { usePartners } from "@/features/stores/useStores";
import { listVendorRates, uploadVendorRates, type RateLine, type RateUploadResult } from "@/services/vendorRates";

const money = (v: string | null) => (v === null ? "—" : `₹${Number(v).toLocaleString("en-IN", { minimumFractionDigits: 2 })}`);
const label = (l: RateLine) => (l.scope === "store" ? `${l.storeName ?? ""} (${l.outletId ?? ""})` : `${l.city ?? ""} (all stores)`);

function Lines({ lines }: { lines: RateLine[] }) {
  return (
    <div className="max-h-72 overflow-auto rounded-lg border border-surface-border">
      <table className="w-full min-w-[420px] text-sm">
        <thead className="sticky top-0 bg-surface-subtle text-left text-[11px] font-bold uppercase tracking-wider text-gray-500">
          <tr><th className="px-3 py-2">Store / city</th><th className="px-3 py-2">Current</th><th className="px-3 py-2">New</th><th className="px-3 py-2">Stores</th></tr>
        </thead>
        <tbody>
          {lines.map((l, i) => (
            <tr key={i} className="border-t border-surface-border/60">
              <td className="break-words px-3 py-2 font-medium text-gray-900">{label(l)}</td>
              <td className="px-3 py-2 tabular-nums text-gray-500">{money(l.oldRate)}</td>
              <td className="px-3 py-2 font-semibold tabular-nums text-gray-900">{money(l.newRate)}</td>
              <td className="px-3 py-2 tabular-nums">{l.scope === "city" ? (l.storesAffected ?? 0) : 1}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** Admin: upload the city-wise vendor rate sheet. A change to an existing rate lists the stores and asks first. */
export function VendorRatesPanel() {
  const { data: partners = [] } = usePartners();
  const qc = useQueryClient();
  const [platform, setPlatform] = useState("blinkit");
  const [file, setFile] = useState<File | null>(null);
  const [effective, setEffective] = useState("");
  const [result, setResult] = useState<RateUploadResult | null>(null);
  const [showCurrent, setShowCurrent] = useState(false);

  const current = useQuery({ queryKey: ["vendor-rates", platform], queryFn: () => listVendorRates(platform), enabled: showCurrent });

  const upload = useMutation({
    mutationFn: (confirm: boolean) => uploadVendorRates(file!, platform, confirm, effective || undefined),
    onSuccess: (r) => {
      setResult(r);
      if (r.applied) {
        pushToast(`Vendor rates saved (${r.new} new, ${r.changed} changed).`, "success");
        void qc.invalidateQueries({ queryKey: ["vendor-rates"] });
      }
    },
  });

  return (
    <section className="rounded-xl border border-surface-border bg-surface shadow-card">
      <header className="border-b border-surface-border/80 px-5 py-4">
        <h3 className="text-sm font-bold text-gray-900">Vendor rates (city-wise)</h3>
        <p className="mt-0.5 text-xs text-gray-500">
          What Veekay charges per bottle. Upload a sheet with <b>City</b> and <b>Rate</b> columns, plus <b>Outlet ID</b> or <b>Store Name</b> for a store with its own rate.
          New rates are added; a change to an existing rate is shown to you first.
        </p>
      </header>
      <div className="flex flex-col gap-4 p-5">
        <div className="grid gap-3 sm:grid-cols-3">
          <label className="flex flex-col gap-1.5 text-[13px] font-semibold text-gray-700">
            Platform
            <SelectField className="h-10 w-full rounded-lg border border-surface-border bg-surface px-3 text-sm" value={platform} onChange={(e) => { setPlatform(e.target.value); setResult(null); }}>
              {(partners.length ? partners : [{ slug: "blinkit", name: "Blinkit" }]).map((p) => <option key={p.slug} value={p.slug}>{p.name}</option>)}
            </SelectField>
          </label>
          <label className="flex flex-col gap-1.5 text-[13px] font-semibold text-gray-700">
            Changes apply from (optional)
            <input type="date" className="h-10 w-full rounded-lg border border-surface-border bg-surface px-3 text-sm" value={effective} onChange={(e) => { setEffective(e.target.value); setResult(null); }} />
          </label>
          <div className="flex items-end">
            <Button
              variant="secondary"
              onClick={() => downloadCsv("vendor-rates-template.csv", ["City", "Rate", "Outlet ID", "Store Name"], [["Delhi", "4.50", "", ""], ["", "5.00", "BLK-1001", ""]])}
            >
              <IconDownload className="h-4 w-4" /> Template
            </Button>
          </div>
        </div>

        <FileDropzone file={file} onPick={(f) => { setFile(f ?? null); setResult(null); }} accept=".csv,.xlsx,.xlsm" hint="Rate sheet (.csv or .xlsx, up to 5 MB)" />

        <div className="flex flex-wrap items-center gap-2">
          <Button onClick={() => upload.mutate(false)} disabled={!file} isLoading={upload.isPending && !result?.needsConfirmation}>Check and upload</Button>
          <Button variant="secondary" onClick={() => setShowCurrent((v) => !v)}>{showCurrent ? "Hide" : "Show"} current rates</Button>
        </div>

        {result?.needsConfirmation && (
          <div role="alert" className="flex flex-col gap-3 rounded-xl border border-status-warning/40 bg-status-warning-soft p-4">
            <p className="flex items-start gap-2 text-sm font-semibold text-status-warning">
              <IconAlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
              {result.changed} rate{result.changed === 1 ? "" : "s"} will change, affecting {result.storesAffected} store{result.storesAffected === 1 ? "" : "s"}
              {" "}(from {new Date(`${result.effectiveFrom}T12:00:00`).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" })}). Nothing has been saved yet. Are you sure?
            </p>
            <Lines lines={result.changes} />
            {result.new > 0 && <p className="text-xs text-gray-600">{result.new} new rate{result.new === 1 ? "" : "s"} will also be added.</p>}
            <div className="flex flex-wrap gap-2">
              <Button onClick={() => upload.mutate(true)} isLoading={upload.isPending}>Yes, update these rates</Button>
              <Button variant="secondary" onClick={() => setResult(null)}>Cancel</Button>
            </div>
          </div>
        )}

        {result?.applied && (
          <p className="flex items-center gap-2 text-sm font-medium text-status-success">
            <IconCheckCircle className="h-4 w-4" /> Saved: {result.new} new, {result.changed} changed, {result.unchanged} unchanged.
          </p>
        )}
        {result && result.warnings.length > 0 && (
          <ul className="list-disc space-y-1 rounded-lg bg-surface-subtle px-4 py-2.5 pl-8 text-xs text-status-warning">
            {result.warnings.map((w, i) => <li key={i}>{w}</li>)}
          </ul>
        )}

        {showCurrent && (
          <div className="max-h-72 overflow-auto rounded-lg border border-surface-border">
            {current.isLoading ? <p className="p-4 text-sm text-gray-500">Loading…</p> : (current.data ?? []).length === 0 ? (
              <p className="p-4 text-sm text-gray-500">No rates uploaded for this platform yet.</p>
            ) : (
              <table className="w-full min-w-[420px] text-sm">
                <thead className="sticky top-0 bg-surface-subtle text-left text-[11px] font-bold uppercase tracking-wider text-gray-500">
                  <tr><th className="px-3 py-2">City / store</th><th className="px-3 py-2">Rate per bottle</th><th className="px-3 py-2">Since</th></tr>
                </thead>
                <tbody>
                  {current.data!.map((r, i) => (
                    <tr key={i} className="border-t border-surface-border/60">
                      <td className="px-3 py-2 font-medium text-gray-900">{r.scope === "store" ? `${r.storeName} (${r.outletId})` : r.city}</td>
                      <td className="px-3 py-2 tabular-nums">{money(r.rate)}</td>
                      <td className="px-3 py-2 text-gray-500">{r.effectiveFrom.startsWith("2000-") ? "start" : r.effectiveFrom}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        )}
      </div>
    </section>
  );
}
