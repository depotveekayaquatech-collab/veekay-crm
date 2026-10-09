import { useEffect, useState, type FormEvent } from "react";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/Button";
import { FileDropzone } from "@/components/ui/FileDropzone";
import { Input } from "@/components/ui/Input";
import { Table, TableEmpty, Td, Th } from "@/components/ui/Table";
import { ApiError, apiBlob, apiRequest } from "@/services/api";
import { pushToast } from "@/lib/toast";
import { RandomCountPanel } from "./RandomCountPanel";

interface Preview {
  file: string;
  rows: number;
  cards: number;
  stores: number;
  entries: number;
  bottles: number;
  unmatched: { row: number; store: string; reason: string }[];
  unmatched_count: number;
  warnings: string[];
  sample: { store: string; code: string; month: string; days: number; bottles: number }[];
}

const KEY = "cardsheet-token";

// The unlock token lives only for this browser tab (and 30 minutes); closing the tab locks the tool again.
function loadToken(): { token: string; exp: number } | null {
  try {
    const raw = sessionStorage.getItem(KEY);
    const t = raw ? (JSON.parse(raw) as { token: string; exp: number }) : null;
    return t && t.exp > Date.now() ? t : null;
  } catch {
    return null;
  }
}

function formData(token: string, file: File): FormData {
  const f = new FormData();
  f.set("token", token);
  f.set("file", file);
  return f;
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-xl border border-surface-border bg-surface px-4 py-3 shadow-card">
      <p className="text-[11px] font-bold uppercase tracking-wider text-gray-500">{label}</p>
      <p className="mt-1 text-xl font-bold tabular-nums text-heading">{value.toLocaleString("en-IN")}</p>
    </div>
  );
}

function LockScreen({ onUnlocked }: { onUnlocked: (token: string, expiresIn: number) => void }) {
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const r = await apiRequest<{ token: string; expires_in: number }>("/developer/card-sheet/unlock", { method: "POST", body: { code }, silent: true });
      onUnlocked(r.token, r.expires_in);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not unlock.");
      setCode("");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="mx-auto flex w-full max-w-sm flex-col gap-4 rounded-xl border border-surface-border bg-surface p-6 shadow-card">
      <div>
        <p className="text-sm font-bold text-heading">Enter the access code</p>
        <p className="mt-1 text-xs text-gray-500">This tool is locked. Unlocks stay open for 30 minutes and every use is recorded in the audit log.</p>
      </div>
      <Input label="Access code" type="password" inputMode="numeric" autoComplete="off" autoFocus value={code} onChange={(e) => setCode(e.target.value)} error={error ?? undefined} />
      <Button type="submit" isLoading={busy} disabled={!code.trim()}>Unlock</Button>
    </form>
  );
}

export function CardSheetPage() {
  const [session, setSession] = useState(loadToken);
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [busy, setBusy] = useState<"preview" | "download" | null>(null);
  const [tab, setTab] = useState<"sheet" | "random">("sheet");

  // Lock again the moment the 30 minutes are up.
  useEffect(() => {
    if (!session) return;
    const id = setTimeout(() => setSession(null), Math.max(0, session.exp - Date.now()));
    return () => clearTimeout(id);
  }, [session]);

  // Lock the moment the user leaves: another browser tab or window comes to the front, or this page is closed / navigated away from.
  useEffect(() => {
    if (!session) return;
    const onHide = () => { if (document.hidden) lock(); };
    document.addEventListener("visibilitychange", onHide);
    return () => {
      document.removeEventListener("visibilitychange", onHide);
      try { sessionStorage.removeItem(KEY); } catch { /* private mode */ }
    };
  }, [session]);

  function lock() {
    try { sessionStorage.removeItem(KEY); } catch { /* private mode */ }
    setSession(null);
    setPreview(null);
    setFile(null);
    setTab("sheet");
  }

  function unlocked(token: string, expiresIn: number) {
    const s = { token, exp: Date.now() + expiresIn * 1000 - 5000 };
    try { sessionStorage.setItem(KEY, JSON.stringify(s)); } catch { /* private mode */ }
    setSession(s);
  }

  async function pick(f: File | undefined) {
    if (!f || !session) return;
    setFile(f);
    setPreview(null);
    setBusy("preview");
    try {
      setPreview(await apiRequest<Preview>("/developer/card-sheet/preview", { method: "POST", body: formData(session.token, f) }));
    } catch (err) {
      if (err instanceof ApiError && err.status === 403) lock();
      setFile(null);
    } finally {
      setBusy(null);
    }
  }

  async function download() {
    if (!file || !session) return;
    setBusy("download");
    try {
      const blob = await apiBlob("/developer/card-sheet/download", { method: "POST", body: formData(session.token, file) });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `Cards_from_sheet_${file.name.replace(/\.[^.]+$/, "")}.pdf`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 30_000);
      pushToast("Cards downloaded. The download is recorded in the audit log.", "success");
    } catch (err) {
      if (err instanceof ApiError && err.status === 403) lock();
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="flex flex-col gap-5">
      <PageHeader
        title="Cards from sheet"
        subtitle="Upload a sheet of store, date and filled bottles to print the store cards with those entries."
        action={session && <Button variant="secondary" onClick={lock}>Lock</Button>}
      />

      {!session ? (
        <LockScreen onUnlocked={unlocked} />
      ) : (
        <>
          <div role="tablist" className="flex gap-1 border-b border-surface-border">
            {([["sheet", "Upload sheet"], ["random", "Random Count PDF Generator"]] as const).map(([id, label]) => (
              <button
                key={id} type="button" role="tab" aria-selected={tab === id} onClick={() => setTab(id)}
                className={`-mb-px border-b-2 px-4 py-2 text-sm font-semibold ${tab === id ? "border-brand-500 text-heading" : "border-transparent text-gray-500 hover:text-gray-800"}`}
              >{label}</button>
            ))}
          </div>

          {tab === "random" && <RandomCountPanel token={session.token} onLocked={lock} />}

          {tab === "sheet" && <>
          <p className="rounded-xl border border-surface-border bg-surface-subtle px-4 py-3 text-sm text-gray-700">
            Standard sheet: <b>Outlet ID</b> and <b>Outlet Name</b> columns, then one column per day (1-Oct, 2-Oct …) with the filled bottles. Other layouts work too (one row per store and date); extra columns, title rows and renamed headers are handled. CSV or Excel, up to 5 MB.
            The cards carry a &ldquo;Source: uploaded sheet&rdquo; footer. The sheet and its entries are used only to make the PDF and are not stored; the audit log keeps just the file name, a fingerprint and the totals.
          </p>

          <FileDropzone file={file} onPick={pick} accept=".csv,.xlsx,.xlsm" hint="CSV or Excel: one row per store per date" />

          {busy === "preview" && <p className="text-sm text-gray-500">Reading the sheet…</p>}

          {preview && (
            <>
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
                <Stat label="Rows read" value={preview.rows} />
                <Stat label="Cards" value={preview.cards} />
                <Stat label="Stores" value={preview.stores} />
                <Stat label="Entries" value={preview.entries} />
                <Stat label="Bottles" value={preview.bottles} />
              </div>

              {preview.warnings.map((w) => <p key={w} className="text-sm text-status-warning">{w}</p>)}

              {preview.unmatched_count > 0 && (
                <div className="rounded-xl border border-status-warning bg-status-warning-soft px-4 py-3 text-sm text-gray-800">
                  <p className="font-semibold">{preview.unmatched_count} row(s) were skipped</p>
                  <ul className="mt-1 list-disc pl-5 text-xs">
                    {preview.unmatched.slice(0, 8).map((u) => <li key={u.row}>Row {u.row} ({u.store}): {u.reason}</li>)}
                  </ul>
                </div>
              )}

              <div className="flex justify-end">
                <Button onClick={download} isLoading={busy === "download"} disabled={preview.cards === 0}>
                  Download {preview.cards} card{preview.cards === 1 ? "" : "s"}
                </Button>
              </div>

              <Table>
                <thead><tr><Th>Store</Th><Th>Code</Th><Th>Month</Th><Th className="text-right">Days</Th><Th className="text-right">Bottles</Th></tr></thead>
                <tbody>
                  {preview.sample.length ? preview.sample.map((c, i) => (
                    <tr key={`${c.code}-${c.month}-${i}`}>
                      <Td className="font-medium text-gray-900">{c.store}</Td>
                      <Td className="font-mono text-xs">{c.code}</Td>
                      <Td>{c.month}</Td>
                      <Td className="text-right tabular-nums">{c.days}</Td>
                      <Td className="text-right tabular-nums">{c.bottles}</Td>
                    </tr>
                  )) : <TableEmpty colSpan={5}>No rows matched a store.</TableEmpty>}
                </tbody>
              </Table>
            </>
          )}
          </>}
        </>
      )}
    </div>
  );
}
