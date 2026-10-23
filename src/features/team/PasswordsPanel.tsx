import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Table, Td, Th, TableEmpty } from "@/components/ui/Table";
import { Skeleton } from "@/components/feedback/Skeleton";
import { ErrorState } from "@/components/feedback/ErrorState";
import { apiRequest } from "@/services/api";
import { pushToast } from "@/lib/toast";

interface PasswordRow {
  id: string;
  employee_code: string;
  full_name: string;
  category: string;
  category_label: string;
  is_active: boolean;
  status: string;
  password: string | null;
  must_change_password: boolean;
  password_changed_at: string | null;
  changed_date_exact: boolean;
  days_since_change: number | null;
}

function ago(days: number | null): string {
  if (days === null) return "—";
  if (days === 0) return "Today";
  if (days === 1) return "1 day ago";
  return `${days} days ago`;
}

function dateOf(iso: string | null): string {
  return iso ? new Date(iso).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" }) : "";
}

/** Developer only: every account's current password and how many days ago it was last changed. Passwords stay hidden until asked for. */
export function PasswordsPanel() {
  const [q, setQ] = useState("");
  const [shown, setShown] = useState<Set<string>>(new Set());
  const [showAll, setShowAll] = useState(false);
  const { data, isLoading, isError, refetch, isFetching } = useQuery({
    queryKey: ["employee-passwords"],
    queryFn: () => apiRequest<PasswordRow[]>("/employees/passwords"),
    staleTime: 0,
    gcTime: 0, // never keep passwords in the cache once the tab is left
  });

  const rows = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return (data ?? []).filter((r) => !needle || r.employee_code.toLowerCase().includes(needle) || r.full_name.toLowerCase().includes(needle));
  }, [data, q]);

  function toggle(id: string) {
    setShown((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  async function copy(pw: string) {
    try {
      await navigator.clipboard.writeText(pw);
      pushToast("Copied.", "success");
    } catch {
      pushToast("Couldn't copy — select the password and copy it manually.", "error");
    }
  }

  const missing = (data ?? []).filter((r) => !r.password).length;

  return (
    <div className="flex flex-col gap-4">
      <div className="rounded-xl bg-status-warning-soft px-4 py-3 text-sm text-status-warning">
        Developer only. Every time this list is opened it is written to the activity log (never the passwords themselves). Don&apos;t share a screenshot of it.
        {missing > 0 && (
          <span className="mt-1 block text-xs">
            {missing} account{missing === 1 ? "" : "s"} show &ldquo;Not recorded yet&rdquo;: the password was set before this view existed. It fills in by
            itself the next time that person signs in, or straight away if you reset it.
          </span>
        )}
      </div>

      <div className="flex flex-wrap items-end gap-3">
        <Input label="Search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="ID or name" className="sm:max-w-xs" />
        <Button variant="secondary" onClick={() => { setShowAll((v) => !v); setShown(new Set()); }}>
          {showAll ? "Hide all passwords" : "Show all passwords"}
        </Button>
        <Button variant="secondary" isLoading={isFetching} onClick={() => void refetch()}>Refresh</Button>
      </div>

      {isLoading && <Skeleton className="h-64" />}
      {isError && <ErrorState message="Couldn't load the passwords." onRetry={() => refetch()} />}

      {data && (
        <Table>
          <thead>
            <tr>
              <Th>Login ID</Th>
              <Th>Name</Th>
              <Th>Category</Th>
              <Th>Status</Th>
              <Th>Current password</Th>
              <Th>Last changed</Th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 && <TableEmpty colSpan={6}>No one matches.</TableEmpty>}
            {rows.map((r) => {
              const visible = showAll || shown.has(r.id);
              return (
                <tr key={r.id}>
                  <Td className="font-medium text-gray-900">{r.employee_code}</Td>
                  <Td>{r.full_name}</Td>
                  <Td>{r.category_label}</Td>
                  <Td>
                    <Badge tone={r.is_active ? "success" : "neutral"}>{r.is_active ? "Active" : r.status === "locked" ? "Locked" : "Deactivated"}</Badge>
                  </Td>
                  <Td>
                    {r.password ? (
                      <div className="flex items-center gap-2 whitespace-nowrap">
                        <code className="select-all rounded bg-surface-subtle px-2 py-1 text-sm font-semibold text-heading">
                          {visible ? r.password : "••••••••••"}
                        </code>
                        <button className="text-xs font-semibold text-brand-600 hover:text-brand-700" onClick={() => toggle(r.id)} disabled={showAll}>
                          {visible ? "Hide" : "Show"}
                        </button>
                        <button className="text-xs font-semibold text-brand-600 hover:text-brand-700" onClick={() => void copy(r.password!)}>
                          Copy
                        </button>
                        {r.must_change_password && <Badge tone="warning">Temporary</Badge>}
                      </div>
                    ) : (
                      <span className="text-xs text-gray-400">Not recorded yet</span>
                    )}
                  </Td>
                  <Td>
                    <span className="font-medium text-gray-900">{ago(r.days_since_change)}</span>
                    <span className="block text-xs text-gray-500">
                      {r.changed_date_exact ? dateOf(r.password_changed_at) : r.password_changed_at ? `Never changed since created ${dateOf(r.password_changed_at)}` : ""}
                    </span>
                  </Td>
                </tr>
              );
            })}
          </tbody>
        </Table>
      )}
    </div>
  );
}
