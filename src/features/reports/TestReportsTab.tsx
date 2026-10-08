import { useRef, useState } from "react";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { FileDropzone } from "@/components/ui/FileDropzone";
import { Select } from "@/components/ui/Select";
import { Table, Td, Th } from "@/components/ui/Table";
import { Skeleton } from "@/components/feedback/Skeleton";
import { ErrorState } from "@/components/feedback/ErrorState";
import { IconAlertTriangle, IconCheckCircle, IconClipboard, IconReport } from "@/components/ui/icons";
import { usePermission } from "@/hooks/usePermission";
import { Panel, StatCard } from "@/features/orders/ui";
import {
  openTestReport,
  periodEndOf,
  periodLabel,
  STATUS_LABEL,
  useRemoveTestReport,
  useTestReports,
  useUploadTestReport,
  type ReportStatus,
  type StateReports,
  type TestReportFile,
} from "@/features/reports/testReports";

const ACCEPT = ".pdf,.jpg,.jpeg,.png,.webp";
const MAX_MB = 8;
const TONE: Record<ReportStatus, "success" | "warning" | "danger" | "neutral"> = {
  VALID: "success",
  EXPIRING: "warning",
  EXPIRED: "danger",
  MISSING: "neutral",
};

function monthValue(offset: number): string {
  const d = new Date();
  d.setMonth(d.getMonth() + offset, 1);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

function when(f: TestReportFile): string {
  if (f.daysLeft < 0) return `expired ${-f.daysLeft} day${f.daysLeft === -1 ? "" : "s"} ago`;
  if (f.daysLeft === 0) return "expires today";
  return `${f.daysLeft} day${f.daysLeft === 1 ? "" : "s"} left`;
}

export function TestReportsTab() {
  const canManage = usePermission("compliance.manage");
  const [picked, setPlatform] = useState("");
  const first = useTestReports(picked || "zepto");
  const platformSlug = picked || first.data?.platforms.find((p) => p.enabled)?.slug || "zepto";
  const { data, isLoading, isError, refetch } = useTestReports(platformSlug);
  const upload = useUploadTestReport();
  const remove = useRemoveTestReport();

  const [state, setState] = useState("");
  const [period, setPeriod] = useState(monthValue(0));
  const [file, setFile] = useState<File | null>(null);
  const [localError, setLocalError] = useState<string | null>(null);
  const [openHistory, setOpenHistory] = useState<Set<string>>(new Set());
  const formRef = useRef<HTMLDivElement>(null);

  const enabled = data?.platform.enabled ?? true;
  const summary = data?.summary;
  const states = data?.states ?? [];
  const end = periodEndOf(period);
  const problems = (summary?.expired ?? 0) + (summary?.expiring ?? 0);

  function pick(f: File | undefined) {
    setLocalError(null);
    if (!f) return;
    if (!/\.(pdf|jpe?g|png|webp)$/i.test(f.name)) return setLocalError("Please choose a PDF or a JPG / PNG / WEBP photo.");
    if (f.size > MAX_MB * 1024 * 1024) return setLocalError(`That file is larger than ${MAX_MB} MB.`);
    setFile(f);
  }

  function submit() {
    if (!file || !state || !period) return;
    upload.mutate(
      { partner: platformSlug, state, periodStart: period, file },
      {
        onSuccess: () => {
          setFile(null);
          setState("");
        },
      },
    );
  }

  function replaceFor(s: StateReports) {
    setState(s.state);
    // Next period follows the current one; a missing / old report starts from this month.
    setPeriod(s.current && s.current.status !== "EXPIRED" ? periodStartAfter(s.current.periodEnd) : monthValue(0));
    formRef.current?.scrollIntoView({ behavior: "smooth", block: "center" });
  }

  function toggleHistory(name: string) {
    setOpenHistory((prev) => {
      const next = new Set(prev);
      if (next.has(name)) next.delete(name);
      else next.add(name);
      return next;
    });
  }

  return (
    <div className="flex flex-col gap-5">
      <div role="tablist" aria-label="Platform" className="inline-flex w-fit gap-1 rounded-xl border border-surface-border bg-surface-muted/70 p-1">
        {(data?.platforms ?? [{ slug: "zepto", name: "Zepto", enabled: true }]).map((p) => (
          <button
            key={p.slug}
            type="button"
            role="tab"
            aria-selected={platformSlug === p.slug}
            disabled={!p.enabled}
            onClick={() => p.enabled && setPlatform(p.slug)}
            title={p.enabled ? undefined : "Test reports are not switched on for this platform yet"}
            className={`flex items-center gap-2 rounded-lg px-4 py-1.5 text-sm font-semibold transition-[color,background-color,box-shadow] ${
              platformSlug === p.slug ? "bg-surface text-brand-700 shadow-sm ring-1 ring-surface-border" : "text-gray-500 hover:text-gray-800"
            } disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:text-gray-500`}
          >
            {p.name}
            {!p.enabled && <span className="rounded-full bg-surface px-1.5 py-px text-[10px] font-bold uppercase tracking-wide text-gray-500">Off</span>}
          </button>
        ))}
      </div>

      {isLoading && <Skeleton className="h-64 !rounded-2xl" />}
      {isError && <ErrorState message="Couldn't load test reports." onRetry={() => refetch()} />}

      {data && !enabled && (
        <div className="flex flex-col items-center gap-3 rounded-2xl border border-dashed border-surface-border bg-surface px-6 py-16 text-center shadow-card">
          <span className="flex h-14 w-14 items-center justify-center rounded-2xl bg-surface-muted text-gray-500">
            <IconReport className="h-7 w-7" aria-hidden="true" />
          </span>
          <p className="text-lg font-bold text-heading">Test reports are off for {data.platform.name}</p>
          <p className="max-w-md text-sm text-gray-500">They are only switched on for Zepto right now.</p>
        </div>
      )}

      {data && enabled && summary && (
        <>
          {problems > 0 && (
            <div role="alert" className="flex flex-wrap items-center gap-3 rounded-2xl border border-status-danger/30 bg-status-danger-soft px-4 py-3.5 text-sm">
              <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-status-danger/15 text-status-danger">
                <IconAlertTriangle className="h-5 w-5" aria-hidden="true" />
              </span>
              <p className="min-w-0 flex-1 text-gray-800">
                {summary.expired > 0 && (
                  <span className="font-bold text-status-danger">
                    {summary.expired} state{summary.expired > 1 ? "s have" : " has"} an expired test report.{" "}
                  </span>
                )}
                {summary.expiring > 0 && (
                  <span className="font-semibold text-status-warning">
                    {summary.expiring} will expire within {data.alertDays} days.{" "}
                  </span>
                )}
                Upload the next 6-month report below.
              </p>
            </div>
          )}

          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <StatCard label="Reports on file" value={summary.reportsTotal} hint={`${summary.statesTotal} states`} tone="brand" icon={IconClipboard} />
            <StatCard label="Valid" value={summary.valid} tone="success" icon={IconCheckCircle} />
            <StatCard label="Expiring soon" value={summary.expiring} hint={`within ${data.alertDays} days`} tone="warning" icon={IconAlertTriangle} />
            <StatCard label="Expired / missing" value={summary.expired + summary.missing} hint={`${summary.expired} expired · ${summary.missing} with none`} tone={summary.expired ? "warning" : "aqua"} icon={IconReport} />
          </div>

          {canManage && (
            <div ref={formRef}>
              <Panel title="Upload a test report" subtitle="Each report is valid for 6 months. Pick the state and the month the 6 months start in.">
                <div className="grid gap-4 lg:grid-cols-[1fr_1.2fr]">
                  <div className="flex flex-col gap-4">
                    <Select
                      label="State"
                      value={state}
                      onChange={(e) => setState(e.target.value)}
                      placeholder="Choose a state…"
                      options={states.map((s) => ({ value: s.state, label: s.state }))}
                    />
                    <div className="flex flex-col gap-1.5">
                      <label htmlFor="tr-period" className="text-sm font-medium text-gray-700">
                        6-month period starts in
                      </label>
                      <input
                        id="tr-period"
                        type="month"
                        value={period}
                        min={monthValue(-24)}
                        max={monthValue(1)}
                        onChange={(e) => setPeriod(e.target.value)}
                        className="h-11 rounded-lg border border-surface-border bg-surface px-3.5 text-sm shadow-sm outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20"
                      />
                      {end && (
                        <p className="text-xs text-gray-500">
                          Covers <span className="font-semibold text-gray-800">{periodLabel(`${period}-01`, end)}</span>. You'll get an alert{" "}
                          {data.alertDays} days before it ends and again once it expires.
                        </p>
                      )}
                    </div>
                  </div>
                  <div className="flex flex-col gap-3">
                    <FileDropzone file={file} onPick={pick} accept={ACCEPT} hint={`PDF or photo · up to ${MAX_MB} MB`} />
                    {(localError || upload.error) && (
                      <p role="alert" className="rounded-lg bg-status-danger-soft px-3 py-2 text-sm text-status-danger">
                        {localError ?? (upload.error instanceof Error ? upload.error.message : "Upload failed.")}
                      </p>
                    )}
                    <div className="flex justify-end">
                      <Button onClick={submit} disabled={!file || !state || !period} isLoading={upload.isPending}>
                        Upload report
                      </Button>
                    </div>
                  </div>
                </div>
              </Panel>
            </div>
          )}

          <div className="stacked-table">
            <Table>
              <thead>
                <tr>
                  <Th>State</Th>
                  <Th>Status</Th>
                  <Th>6-month period</Th>
                  <Th>Validity</Th>
                  <Th>Uploaded</Th>
                  <Th>Actions</Th>
                </tr>
              </thead>
              <tbody>
                {states.length === 0 && (
                  <tr>
                    <td colSpan={6} className="px-4 py-10 text-center text-sm text-gray-500">
                      No states yet — {data.platform.name} has no live stores.
                    </td>
                  </tr>
                )}
                {states.flatMap((s) => {
                  const c = s.current;
                  const rows = [
                    <tr key={s.state}>
                      <Td data-label="State">
                        <div className="font-semibold text-gray-900">{s.state}</div>
                        <div className="text-xs text-gray-500">{s.stores} live store{s.stores === 1 ? "" : "s"}</div>
                      </Td>
                      <Td data-label="Status">
                        <Badge tone={TONE[s.status]}>{STATUS_LABEL[s.status]}</Badge>
                      </Td>
                      <Td data-label="6-month period">{c ? periodLabel(c.periodStart, c.periodEnd) : "—"}</Td>
                      <Td data-label="Validity">
                        {c ? (
                          <span className={c.status === "EXPIRED" ? "font-semibold text-status-danger" : c.status === "EXPIRING" ? "font-semibold text-status-warning" : "text-gray-700"}>{when(c)}</span>
                        ) : (
                          "—"
                        )}
                      </Td>
                      <Td data-label="Uploaded">
                        {c ? (
                          <>
                            <div className="text-sm">{new Date(c.uploadedAt).toLocaleDateString()}</div>
                            {c.uploadedBy && <div className="text-xs text-gray-500">{c.uploadedBy}</div>}
                          </>
                        ) : (
                          "—"
                        )}
                      </Td>
                      <Td data-label="Actions">
                        <div className="flex flex-wrap items-center gap-2">
                          {c && (
                            <Button size="sm" variant="secondary" onClick={() => void openTestReport(c.id)}>
                              View
                            </Button>
                          )}
                          {canManage && (
                            <Button size="sm" variant={s.status === "EXPIRED" || s.status === "MISSING" ? "primary" : "ghost"} onClick={() => replaceFor(s)}>
                              {c ? (s.status === "VALID" ? "Add next" : "Renew") : "Upload"}
                            </Button>
                          )}
                          {canManage && c && (
                            <button
                              type="button"
                              onClick={() => window.confirm(`Remove the ${s.state} report (${periodLabel(c.periodStart, c.periodEnd)})? The file stays archived.`) && remove.mutate(c.id)}
                              className="text-xs font-semibold text-status-danger hover:underline"
                            >
                              Remove
                            </button>
                          )}
                          {s.history.length > 0 && (
                            <button type="button" onClick={() => toggleHistory(s.state)} aria-expanded={openHistory.has(s.state)} className="text-xs font-semibold text-gray-500 hover:text-gray-800">
                              {openHistory.has(s.state) ? "Hide" : "Earlier"} ({s.history.length})
                            </button>
                          )}
                        </div>
                      </Td>
                    </tr>,
                  ];
                  if (openHistory.has(s.state)) {
                    s.history.forEach((h) =>
                      rows.push(
                        <tr key={h.id} className="bg-surface-subtle/60">
                          <Td data-label="State"><span className="pl-4 text-xs text-gray-500">↳ earlier report</span></Td>
                          <Td data-label="Status"><Badge tone={TONE[h.status]}>{STATUS_LABEL[h.status]}</Badge></Td>
                          <Td data-label="6-month period">{periodLabel(h.periodStart, h.periodEnd)}</Td>
                          <Td data-label="Validity"><span className="text-gray-500">{when(h)}</span></Td>
                          <Td data-label="Uploaded">{new Date(h.uploadedAt).toLocaleDateString()}</Td>
                          <Td data-label="Actions">
                            <Button size="sm" variant="secondary" onClick={() => void openTestReport(h.id)}>View</Button>
                          </Td>
                        </tr>,
                      ),
                    );
                  }
                  return rows;
                })}
              </tbody>
            </Table>
          </div>
        </>
      )}
    </div>
  );
}

/** The month right after a period ends, as yyyy-mm (the natural start of the next 6 months). */
function periodStartAfter(endIso: string): string {
  const d = new Date(`${endIso}T12:00:00`);
  d.setDate(d.getDate() + 1);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}
