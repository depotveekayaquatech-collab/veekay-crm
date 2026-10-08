import { useState } from "react";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/Button";
import { Pagination } from "@/components/ui/Pagination";
import { Table, Td, TableEmpty, Th } from "@/components/ui/Table";
import { SearchBox, SegmentedControl } from "@/features/orders/ui";
import { AdjustTab } from "@/features/datasync/AdjustTab";
import { SyncTab } from "@/features/datasync/SyncTab";
import { Badge } from "@/components/ui/Badge";
import { Input } from "@/components/ui/Input";
import { inr } from "@/features/cash/api";
import { Skeleton } from "@/components/feedback/Skeleton";
import { HISTORY_PAGE_SIZE, downloadAnalysisSheet, downloadHistorySheet, useAnalysis, useHistory, useSyncRuns, when } from "@/features/datasync/cashApi";

const day = (iso: string) => new Date(`${iso}T00:00:00`).toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" });

function HistoryTab() {
  const [page, setPage] = useState(1);
  const [q, setQ] = useState("");
  const { data } = useHistory(page, q);
  const { data: runs = [] } = useSyncRuns();
  const [busy, setBusy] = useState(false);
  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center gap-3">
        <SearchBox className="min-w-[220px] flex-1" value={q} onChange={(v) => { setQ(v); setPage(1); }} placeholder="Search outlet name or ID" />
        <Button variant="secondary" isLoading={busy} onClick={async () => { setBusy(true); try { await downloadHistorySheet(); } catch { /* shown */ } finally { setBusy(false); } }}>
          Download history sheet
        </Button>
      </div>
      <Table>
        <thead>
          <tr>
            <Th>When</Th><Th>Developer</Th><Th>Outlet</Th><Th>Purchase date</Th><Th className="text-right">Amount</Th><Th className="text-right">Price</Th>
            <Th className="text-center">Auto</Th><Th className="text-center">Final</Th><Th className="text-center">Before → After</Th><Th>Source</Th>
          </tr>
        </thead>
        <tbody>
          {data?.items.length ? (
            data.items.map((h) => (
              <tr key={h.id}>
                <Td className="whitespace-nowrap">{when(h.createdAt)}{h.syncCode && <div className="font-mono text-xs text-gray-500">{h.syncCode} · {h.purchaseCode}</div>}</Td>
                <Td>{h.developer}</Td>
                <Td><span className="font-medium text-gray-900">{h.outletName}</span><div className="text-xs text-gray-500">{h.outletCode}</div></Td>
                <Td className="whitespace-nowrap">{day(h.purchaseDate)}</Td>
                <Td className="text-right tabular-nums">₹{h.amount}</Td>
                <Td className="text-right tabular-nums">₹{h.pricePerItem}</Td>
                <Td className="text-center tabular-nums">{h.autoQty}</Td>
                <Td className="text-center font-semibold tabular-nums">{h.finalQty}</Td>
                <Td className="whitespace-nowrap text-center tabular-nums">{h.previousQty} → {h.finalOrderQty}</Td>
                <Td>{h.source}</Td>
              </tr>
            ))
          ) : (
            <TableEmpty colSpan={10}>No adjustments recorded yet.</TableEmpty>
          )}
        </tbody>
      </Table>
      {data && <Pagination page={page} pageSize={HISTORY_PAGE_SIZE} total={data.total} onPageChange={setPage} />}

      <section className="flex flex-col gap-3">
        <h3 className="text-base font-bold text-heading">Sync history</h3>
        <Table>
          <thead>
            <tr><Th>Sync</Th><Th>Time</Th><Th>Developer</Th><Th className="text-right">Found</Th><Th className="text-right">New</Th><Th className="text-right">Changed</Th><Th className="text-right">Already processed</Th><Th className="text-right">Applied</Th></tr>
          </thead>
          <tbody>
            {runs.length ? runs.map((r) => (
              <tr key={r.syncId}>
                <Td className="font-mono text-xs">{r.syncCode}</Td><Td className="whitespace-nowrap">{when(r.syncedAt)}</Td><Td>{r.developer}</Td>
                <Td className="text-right tabular-nums">{r.recordsFound}</Td><Td className="text-right tabular-nums">{r.newRecords}</Td><Td className="text-right tabular-nums">{r.changedRecords}</Td>
                <Td className="text-right tabular-nums">{r.alreadyProcessed}</Td><Td className="text-right tabular-nums">{r.applied}</Td>
              </tr>
            )) : <TableEmpty colSpan={8}>No syncs yet.</TableEmpty>}
          </tbody>
        </Table>
      </section>
    </div>
  );
}

function AnalysisTab() {
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [open, setOpen] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const { data, isLoading } = useAnalysis(start, end);
  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-end gap-3">
        <div className="w-40"><Input label="From" type="date" value={start} max={end || undefined} onChange={(e) => setStart(e.target.value)} /></div>
        <div className="w-40"><Input label="To" type="date" value={end} min={start || undefined} onChange={(e) => setEnd(e.target.value)} /></div>
        {(start || end) && <Button variant="ghost" onClick={() => { setStart(""); setEnd(""); }}>All time</Button>}
        <Button className="ml-auto" isLoading={busy} onClick={async () => { setBusy(true); try { await downloadAnalysisSheet(start, end); } catch { /* shown */ } finally { setBusy(false); } }}>
          Download analysis sheet
        </Button>
      </div>
      {isLoading || !data ? (
        <Skeleton className="h-64 w-full" />
      ) : (
        <>
          <p className="text-sm text-gray-600">
            <b>{data.totalPurchases}</b> store cash purchases (₹{data.totalAmount}) across <b>{data.vendorsCount}</b> vendors · average {data.averagePurchases} per vendor ·{" "}
            <Badge tone="danger">{data.high} high</Badge> <Badge tone="warning">{data.watch} watch</Badge>
          </p>
          <Table>
            <thead>
              <tr><Th>#</Th><Th>Flag</Th><Th>Vendor</Th><Th className="text-right">Cash purchases</Th><Th className="text-right">Amount</Th><Th className="text-center">Stores</Th><Th>Store names</Th></tr>
            </thead>
            <tbody>
              {data.vendors.length ? data.vendors.map((v) => (
                <tr key={v.vendor} className={v.flag === "HIGH" ? "bg-status-danger-soft/40" : v.flag === "WATCH" ? "bg-status-warning-soft/40" : undefined}>
                  <Td className="tabular-nums">{v.rank}</Td>
                  <Td>{v.flag ? <Badge tone={v.flag === "HIGH" ? "danger" : "warning"}>{v.flag === "HIGH" ? "High" : "Watch"}</Badge> : <span className="text-gray-400">—</span>}</Td>
                  <Td><span className="font-medium text-gray-900">{v.vendor}</span>{v.vendorNumber && <div className="text-xs text-gray-500">{v.vendorNumber}</div>}</Td>
                  <Td className="text-right font-semibold tabular-nums">{v.purchases}</Td>
                  <Td className="text-right tabular-nums">{inr(v.amount)}</Td>
                  <Td className="text-center tabular-nums">{v.storesWithPurchases} / {v.totalStores}</Td>
                  <Td className="max-w-md text-xs text-gray-600">
                    {(open === v.vendor ? v.stores : v.stores.slice(0, 3)).map((s) => `${s.outletName} (${s.purchases})`).join(", ")}
                    {v.stores.length > 3 && (
                      <button type="button" className="ml-1 font-semibold text-brand-600" onClick={() => setOpen(open === v.vendor ? null : v.vendor)}>
                        {open === v.vendor ? "less" : `+${v.stores.length - 3} more`}
                      </button>
                    )}
                  </Td>
                </tr>
              )) : <TableEmpty colSpan={7}>No store cash purchases in this period.</TableEmpty>}
            </tbody>
          </Table>
          <p className="text-xs text-gray-500">High = at least 3 purchases and 1.5× the average vendor. Watch = at least 2 and above average. The downloaded sheet adds a per-store breakdown.</p>
        </>
      )}
    </div>
  );
}

/** Developer tools: cash-purchase adjustments to the order sheet. Reached only with the reserved `cash.adjust` permission. */
export function CashToolsPage() {
  const [tab, setTab] = useState<"adjust" | "sync" | "history" | "analysis">("sync");
  return (
    <div className="flex flex-col gap-6">
      <PageHeader title="Cash purchase" subtitle="Add cash-bought bottles on top of the employees' order entries. Developer only." />
      <SegmentedControl
        label="Section"
        value={tab}
        onChange={setTab}
        options={[
          { value: "sync", label: "Sync & review" },
          { value: "adjust", label: "Manual adjustment" },
          { value: "history", label: "History" },
          { value: "analysis", label: "Analysis" },
        ]}
      />
      {tab === "adjust" && <AdjustTab />}
      {tab === "sync" && <SyncTab />}
      {tab === "history" && <HistoryTab />}
      {tab === "analysis" && <AnalysisTab />}
    </div>
  );
}
