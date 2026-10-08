import { useState } from "react";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/Button";
import { IconRefresh, IconUpload } from "@/components/ui/icons";
import { ImportOrdersModal } from "@/features/orders/ImportOrdersModal";
import { useSyncOrders } from "@/features/orders/useOrders";
import { ImportStoresModal } from "@/features/stores/ImportStoresModal";
import { useStoreMutations } from "@/features/stores/useStores";

interface Result {
  platform: string;
  created: number;
  updated: number;
  unchanged: number;
  rowsRead: number;
  warnings: string[];
}

function Results({ title, results, onDismiss }: { title: string; results: Result[]; onDismiss: () => void }) {
  const warnings = results.flatMap((r) => r.warnings.map((w) => `${r.platform}: ${w}`));
  return (
    <div className="flex flex-col gap-2 rounded-xl bg-surface-subtle p-4 text-sm">
      <div className="flex items-center justify-between gap-3">
        <p className="font-bold text-heading">{title}</p>
        <button type="button" onClick={onDismiss} className="text-xs font-semibold text-gray-500 hover:text-gray-800">
          Dismiss
        </button>
      </div>
      <ul className="flex flex-col gap-1 text-gray-600">
        {results.map((r) => (
          <li key={r.platform}>
            <span className="font-bold capitalize text-gray-900">{r.platform}</span>: +{r.created} new · {r.updated} updated · {r.unchanged} unchanged · {r.rowsRead} rows read
          </li>
        ))}
      </ul>
      {warnings.length > 0 && (
        <ul className="max-h-40 list-disc space-y-1 overflow-auto rounded-lg bg-status-warning-soft px-4 py-2.5 pl-8 text-xs text-status-warning">
          {warnings.map((w, i) => (
            <li key={i}>{w}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

function Card({ title, description, children }: { title: string; description: string; children: React.ReactNode }) {
  return (
    <section className="flex flex-col gap-4 rounded-2xl border border-surface-border bg-surface p-5 shadow-card">
      <div>
        <h3 className="text-base font-bold text-heading">{title}</h3>
        <p className="mt-1 text-sm text-gray-500">{description}</p>
      </div>
      {children}
    </section>
  );
}

/** Bulk sheet tools. Only the developer role reaches this page; the server enforces it (`sheets.sync`). */
export function DataSyncPage() {
  const [importStores, setImportStores] = useState(false);
  const [importOrders, setImportOrders] = useState(false);
  const { sync: syncStores } = useStoreMutations();
  const syncOrders = useSyncOrders();

  return (
    <div className="flex flex-col gap-6">
      <PageHeader title="Data sync" subtitle="Bulk sheet tools for stores and orders. Everyone else adds stores one by one." />
      <div className="grid gap-5 lg:grid-cols-2">
        <Card title="Stores" description="Pull the outlet list from the connected Google Sheet, or upload a .csv / .xlsx file.">
          <div className="flex flex-wrap gap-2">
            <Button variant="secondary" onClick={() => syncStores.mutate(undefined)} isLoading={syncStores.isPending}>
              <IconRefresh className="h-4 w-4" aria-hidden="true" />
              Sync from Sheet
            </Button>
            <Button variant="secondary" onClick={() => setImportStores(true)}>
              <IconUpload className="h-4 w-4" aria-hidden="true" />
              Import file
            </Button>
          </div>
          {syncStores.data && <Results title="Last store sync" results={syncStores.data} onDismiss={() => syncStores.reset()} />}
        </Card>
        <Card title="Orders" description="Pull daily bottle counts from the connected Google Sheet, or upload an order sheet.">
          <div className="flex flex-wrap gap-2">
            <Button variant="secondary" onClick={() => syncOrders.mutate({})} isLoading={syncOrders.isPending}>
              <IconRefresh className="h-4 w-4" aria-hidden="true" />
              Sync from Sheet
            </Button>
            <Button variant="secondary" onClick={() => setImportOrders(true)}>
              <IconUpload className="h-4 w-4" aria-hidden="true" />
              Import file
            </Button>
          </div>
          {syncOrders.data && <Results title="Last order sync" results={syncOrders.data} onDismiss={() => syncOrders.reset()} />}
        </Card>
      </div>
      {importStores && <ImportStoresModal onClose={() => setImportStores(false)} />}
      {importOrders && <ImportOrdersModal onClose={() => setImportOrders(false)} />}
    </div>
  );
}
