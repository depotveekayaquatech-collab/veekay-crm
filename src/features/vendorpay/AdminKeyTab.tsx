import { useState } from "react";
import { ErrorState } from "@/components/feedback/ErrorState";
import { Skeleton } from "@/components/feedback/Skeleton";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { generateKey, useKeyInfo } from "@/features/vendorpay/adminApi";
import { copyText } from "@/lib/clipboard";
import { pushToast } from "@/lib/toast";

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-0.5 sm:flex-row sm:gap-4">
      <dt className="w-44 shrink-0 text-xs font-bold text-gray-500">{label}</dt>
      <dd className="min-w-0 break-words text-sm text-gray-800">{children}</dd>
    </div>
  );
}

export function AdminKeyTab() {
  const { data, isLoading, isError, refetch } = useKeyInfo();
  const [fresh, setFresh] = useState<{ key: string; note: string } | null>(null);
  const [busy, setBusy] = useState(false);

  async function make() {
    setBusy(true);
    try {
      setFresh(await generateKey());
    } catch {
      /* the API layer already showed the reason */
    } finally {
      setBusy(false);
    }
  }

  if (isError) return <ErrorState message="Couldn't load the connection details." onRetry={() => void refetch()} />;
  if (isLoading || !data) return <Skeleton className="h-48 w-full" />;

  return (
    <div className="flex max-w-3xl flex-col gap-5">
      <dl className="flex flex-col gap-3 rounded-xl border border-surface-border bg-surface p-4">
        <Row label="Connection">
          <Badge tone={data.configured ? "success" : "warning"}>{data.configured ? "A key is set on the server" : "No key set: Busy cannot send yet"}</Badge>
        </Row>
        <Row label="Address (POST)"><code>{data.endpointPath}</code> on the API server</Row>
        <Row label="Header"><code>{data.header}</code>: the key</Row>
        <Row label="Server setting"><code>{data.envVariable}</code></Row>
        <Row label="Vendor code format"><code>{data.vendorCodeRegex}</code> (the last word of the account name)</Row>
        <Row label="Out-of-date warning">After {data.staleHours} hours without a successful update</Row>
      </dl>

      <p className="text-sm text-gray-600">{data.instructions}</p>

      <div className="flex flex-col gap-3">
        <div>
          <Button variant="secondary" isLoading={busy} onClick={() => void make()}>
            Generate a new key
          </Button>
        </div>
        {fresh && (
          <div className="flex flex-col gap-2 rounded-xl bg-surface-subtle p-4">
            <code className="break-all text-sm font-semibold text-heading">{fresh.key}</code>
            <p className="text-xs text-gray-600">{fresh.note}</p>
            <div>
              <Button size="sm" variant="secondary" onClick={async () => pushToast((await copyText(fresh.key)) ? "Key copied." : "Couldn't copy. Select it and copy by hand.", "info")}>
                Copy key
              </Button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
