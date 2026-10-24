import { useEffect, useState, type FormEvent } from "react";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { ApiError, apiRequest } from "@/services/api";
import { RandomCountPanel } from "./RandomCountPanel";
import { RandomSheetPanel } from "./RandomSheetPanel";

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

/** Random Card PDF (many outlets from a sheet, or one store). Level 3 (Reviewer) and above, and still behind the access code. */
export function CardSheetPage() {
  const [session, setSession] = useState(loadToken);
  const [mode, setMode] = useState<"sheet" | "one">("sheet");

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
    setMode("sheet");
  }

  function unlocked(token: string, expiresIn: number) {
    const s = { token, exp: Date.now() + expiresIn * 1000 - 5000 };
    try { sessionStorage.setItem(KEY, JSON.stringify(s)); } catch { /* private mode */ }
    setSession(s);
  }

  return (
    <div className="flex flex-col gap-5">
      <PageHeader
        title="Random Card PDF"
        subtitle="Upload a sheet of outlets and totals, or pick one store, and print the store cards with the total shared out across the dates you choose."
        action={session && <Button variant="secondary" onClick={lock}>Lock</Button>}
      />

      {!session ? (
        <LockScreen onUnlocked={unlocked} />
      ) : (
        <>
          <div role="tablist" className="flex w-fit gap-1 rounded-lg bg-surface-muted p-1">
            {([["sheet", "From a sheet (many outlets)"], ["one", "One store"]] as const).map(([id, label]) => (
              <button
                key={id} type="button" role="tab" aria-selected={mode === id} onClick={() => setMode(id)}
                className={`rounded-md px-3 py-1.5 text-sm font-semibold ${mode === id ? "bg-surface text-heading shadow-sm" : "text-gray-500 hover:text-gray-800"}`}
              >{label}</button>
            ))}
          </div>
          {mode === "sheet" ? <RandomSheetPanel token={session.token} onLocked={lock} /> : <RandomCountPanel token={session.token} onLocked={lock} />}
        </>
      )}
    </div>
  );
}
