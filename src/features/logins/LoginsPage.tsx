import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Modal } from "@/components/ui/Modal";
import { Pagination } from "@/components/ui/Pagination";
import { Table, TableEmpty, Td, Th } from "@/components/ui/Table";
import { ErrorState } from "@/components/feedback/ErrorState";
import { Skeleton } from "@/components/feedback/Skeleton";
import { SearchBox, SegmentedControl } from "@/features/orders/ui";
import { PAGE_SIZE, downloadLogins, resetLoginPassword, useLoginDetail, useLogins, type LoginAccount, type LoginFilters, type PasswordResult } from "@/features/logins/api";
import { useAuth } from "@/features/auth/useAuth";
import { GenerateLoginsModal } from "@/features/logins/GenerateLoginsModal";
import { useDebounced } from "@/hooks/useDebounced";
import { pushToast } from "@/lib/toast";

const kindLabel = (k: string) => (k === "vendor" ? "Vendor" : "POC");

function Stat({ label, value }: { label: string; value: number | undefined }) {
  return (
    <div className="rounded-xl border border-surface-border bg-surface px-4 py-3 shadow-card">
      <p className="text-[11px] font-bold text-gray-500">{label}</p>
      <p className="mt-1 text-xl font-bold tabular-nums text-heading">{value?.toLocaleString("en-IN") ?? "—"}</p>
    </div>
  );
}

function copy(text: string) {
  navigator.clipboard?.writeText(text).then(() => pushToast("Copied.", "success"), () => undefined);
}

function PasswordSection({ account }: { account: LoginAccount }) {
  const { hasPermission } = useAuth();
  const queryClient = useQueryClient();
  const [value, setValue] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<PasswordResult | null>(null);
  const [default_, setDefault] = useState(account.mustChangePassword);
  if (!hasPermission("logins.manage")) return null;

  async function save() {
    setBusy(true);
    try {
      setResult(await resetLoginPassword(account.id, value.trim() || undefined));
      setValue("");
      setDefault(false);
      void queryClient.invalidateQueries({ queryKey: ["logins"] });
    } catch {
      /* the API layer already showed the reason */
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col gap-3 rounded-xl border border-surface-border bg-surface-subtle p-4">
      <div className="flex flex-wrap items-center gap-2">
        <p className="text-sm font-bold text-heading">Password</p>
        {default_ ? <Badge tone="warning">Still the standard starting password</Badge> : <Badge tone="success">Custom password set</Badge>}
      </div>
      <p className="text-xs text-gray-500">Setting a password signs this person out of every phone and unlocks the account. Leave the box empty for a random one. Passwords are stored only as a hash, so this is the one time you see it.</p>
      <div className="flex flex-wrap items-end gap-3">
        <div className="min-w-[220px] flex-1"><Input label="New password (6+ characters)" value={value} onChange={(e) => setValue(e.target.value)} autoComplete="off" /></div>
        <Button onClick={save} isLoading={busy} disabled={value.length > 0 && value.trim().length < 6}>{value.trim() ? "Set password" : "Generate random"}</Button>
      </div>
      {result && (
        <div className="flex flex-wrap items-center gap-3 rounded-lg bg-status-success-soft px-3 py-2.5 text-sm">
          <span className="text-gray-700">{result.generated ? "New random password" : "Password set"}:</span>
          <code className="rounded bg-surface px-2 py-1 font-mono text-sm font-bold text-heading">{result.password}</code>
          <Button size="sm" variant="secondary" onClick={() => copy(result.password)}>Copy</Button>
        </div>
      )}
    </div>
  );
}

function AccountModal({ account, onClose }: { account: LoginAccount; onClose: () => void }) {
  const { data, isLoading } = useLoginDetail(account.id);
  return (
    <Modal open onClose={onClose} title={account.fullName} size="lg" description={`${kindLabel(account.kind)} · ${account.email}`}>
      <div className="flex flex-col gap-4">
        <div className="flex flex-wrap items-center gap-2">
          <Button size="sm" variant="secondary" onClick={() => copy(account.email)}>Copy login</Button>
          {account.phone && <span className="text-sm text-gray-600">{account.phone}</span>}
        </div>
        <PasswordSection account={account} />
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
  const [generating, setGenerating] = useState(false);
  const { hasPermission } = useAuth();
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
      <div className="flex flex-wrap justify-end gap-2">
        {hasPermission("sheets.sync") && <Button variant="secondary" onClick={() => setGenerating(true)}>Create logins from stores</Button>}
        <Button variant="secondary" onClick={download} isLoading={downloading}>Download list</Button>
      </div>
      {generating && <GenerateLoginsModal onClose={() => setGenerating(false)} />}

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
