import { useState } from "react";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import { Pagination } from "@/components/ui/Pagination";
import { Table, TableEmpty, Td, Th } from "@/components/ui/Table";
import { ErrorState } from "@/components/feedback/ErrorState";
import { Skeleton } from "@/components/feedback/Skeleton";
import { SearchBox, SegmentedControl } from "@/features/orders/ui";
import { PAGE_SIZE, downloadLogins, useLoginDetail, useLogins, type LoginAccount, type LoginFilters } from "@/features/logins/api";
import { useDebounced } from "@/hooks/useDebounced";
import { pushToast } from "@/lib/toast";

const kindLabel = (k: string) => (k === "vendor" ? "Vendor" : "POC");

function Stat({ label, value }: { label: string; value: number | undefined }) {
  return (
    <div className="rounded-xl border border-surface-border bg-surface px-4 py-3 shadow-card">
      <p className="text-[11px] font-bold uppercase tracking-wider text-gray-500">{label}</p>
      <p className="mt-1 text-xl font-bold tabular-nums text-heading">{value?.toLocaleString("en-IN") ?? "—"}</p>
    </div>
  );
}

function copy(text: string) {
  navigator.clipboard?.writeText(text).then(() => pushToast("Copied.", "success"), () => undefined);
}

function AccountModal({ account, onClose }: { account: LoginAccount; onClose: () => void }) {
  const { data, isLoading } = useLoginDetail(account.id);
  return (
    <Modal open onClose={onClose} title={account.fullName} size="lg" description={`${kindLabel(account.kind)} · ${account.email}`}>
      <div className="flex flex-col gap-4">
        <div className="flex flex-wrap items-center gap-2">
          <Button size="sm" variant="secondary" onClick={() => copy(account.email)}>Copy login</Button>
          {account.mustChangePassword ? <Badge tone="warning">Must choose a new password at first login</Badge> : <Badge tone="success">Password changed</Badge>}
          {account.phone && <span className="text-sm text-gray-600">{account.phone}</span>}
        </div>
        {isLoading ? <Skeleton className="h-32 w-full" /> : (
          <Table>
            <thead><tr><Th>Store</Th><Th>Code</Th><Th>Platform</Th><Th>City</Th></tr></thead>
            <tbody>
              {data?.stores.length ? data.stores.map((s) => (
                <tr key={s.id}>
                  <Td className="font-medium text-gray-900">{s.name}</Td>
                  <Td className="font-mono text-xs">{s.code}</Td>
                  <Td className="capitalize">{s.platform ?? "—"}</Td>
                  <Td>{[s.city, s.state].filter(Boolean).join(", ") || "—"}</Td>
                </tr>
              )) : <TableEmpty colSpan={4}>No stores linked.</TableEmpty>}
            </tbody>
          </Table>
        )}
      </div>
    </Modal>
  );
}

/** The vendor / POC logins, shown as a tab of Users & access. These people are not part of the team. */
export function LoginsPanel() {
  const [kind, setKind] = useState<LoginFilters["kind"]>("");
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  const [open, setOpen] = useState<LoginAccount | null>(null);
  const [downloading, setDownloading] = useState(false);
  const filters: LoginFilters = { kind, platform: "", q: useDebounced(q) };
  const { data, isLoading, isError, refetch, isFetching } = useLogins(filters, page);

  async function download() {
    setDownloading(true);
    try {
      await downloadLogins(filters);
    } catch {
      /* the API layer already showed the reason */
    } finally {
      setDownloading(false);
    }
  }

  return (
    <div className="flex flex-col gap-5">
      <div className="flex justify-end">
        <Button variant="secondary" onClick={download} isLoading={downloading}>Download list</Button>
      </div>

      <div className="grid gap-3 sm:grid-cols-3">
        <Stat label="All logins" value={data ? data.vendors + data.pocs : undefined} />
        <Stat label="Vendors" value={data?.vendors} />
        <Stat label="POCs" value={data?.pocs} />
      </div>

      <div className="flex flex-wrap items-end gap-3">
        <SegmentedControl
          label="Type"
          value={kind}
          onChange={(v) => { setKind(v); setPage(1); }}
          options={[{ value: "", label: "All" }, { value: "vendor", label: "Vendors" }, { value: "poc", label: "POCs" }]}
        />
        <SearchBox className="min-w-[220px] flex-1" value={q} onChange={(v) => { setQ(v); setPage(1); }} placeholder="Search name, login or phone" />
      </div>

      {isError ? (
        <ErrorState message="Could not load the logins." onRetry={() => refetch()} />
      ) : isLoading ? (
        <Skeleton className="h-64 w-full" />
      ) : (
        <div className={isFetching ? "opacity-70 transition-opacity" : "transition-opacity"}>
          <Table>
            <thead>
              <tr><Th>Type</Th><Th>Login</Th><Th>Name</Th><Th>Phone</Th><Th>Platform</Th><Th className="text-right">Stores</Th></tr>
            </thead>
            <tbody>
              {data?.items.length ? data.items.map((a) => (
                <tr key={a.id} className="cursor-pointer hover:bg-surface-subtle" onClick={() => setOpen(a)}>
                  <Td><Badge tone={a.kind === "vendor" ? "info" : "success"}>{kindLabel(a.kind)}</Badge></Td>
                  <Td className="whitespace-nowrap font-mono text-xs text-gray-900">{a.email}</Td>
                  <Td className="font-medium text-gray-900">{a.fullName}</Td>
                  <Td className="whitespace-nowrap">{a.phone ?? "—"}</Td>
                  <Td className="capitalize">{a.platforms.join(", ") || "—"}</Td>
                  <Td className="text-right tabular-nums">{a.storeCount}</Td>
                </tr>
              )) : <TableEmpty colSpan={6}>{q || kind ? "No logins match." : "No logins created yet."}</TableEmpty>}
            </tbody>
          </Table>
        </div>
      )}
      {data && <Pagination page={page} pageSize={PAGE_SIZE} total={data.total} onPageChange={setPage} />}
      {open && <AccountModal account={open} onClose={() => setOpen(null)} />}
    </div>
  );
}
