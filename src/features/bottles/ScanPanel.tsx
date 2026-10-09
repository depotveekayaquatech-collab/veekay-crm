import { useCallback, useEffect, useRef, useState } from "react";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { SegmentedControl } from "@/features/orders/ui";
import { ApiError } from "@/services/api";
import { useScan, useScanStores, type Direction, type ScanResult } from "@/features/bottles/api";
import { usePersistentState } from "@/hooks/usePersistentState";

interface Entry {
  key: number;
  serial: string;
  direction: Direction;
  ok: boolean;
  message: string;
  warning?: string | null;
  store?: string | null;
}

// BarcodeDetector is built into Chrome / Edge / Android browsers; elsewhere staff type the code or use a scanner gun.
interface Detector {
  detect(src: HTMLVideoElement): Promise<{ rawValue: string }[]>;
}
declare global {
  interface Window {
    BarcodeDetector?: new (o: { formats: string[] }) => Detector;
  }
}

export function ScanPanel() {
  const { data: stores } = useScanStores();
  const [storeId, setStoreId] = usePersistentState<string>("bottle-scan-store", "");
  const [direction, setDirection] = usePersistentState<Direction>("bottle-scan-direction", "IN");
  const [text, setText] = useState("");
  const [log, setLog] = useState<Entry[]>([]);
  const [camera, setCamera] = useState(false);
  const scan = useScan();
  const inputRef = useRef<HTMLInputElement>(null);
  const counter = useRef(0);
  const needStore = direction === "IN" && !storeId;

  const submit = useCallback(
    (raw: string) => {
      const serial = raw.trim();
      if (!serial) return;
      const entry = (ok: boolean, message: string, extra: Partial<Entry> = {}) =>
        setLog((l) => [{ key: ++counter.current, serial, direction, ok, message, ...extra }, ...l].slice(0, 30));
      scan.mutate(
        { serial, direction, storeId },
        {
          onSuccess: (r: ScanResult) => {
            if (navigator.vibrate) navigator.vibrate(r.warning ? [80, 60, 80] : 60);
            entry(true, r.duplicate ? "Already recorded" : direction === "IN" ? "Scanned IN" : "Scanned OUT", {
              warning: r.warning,
              store: r.scan.storeName,
              serial: r.bottle.serial,
            });
          },
          onError: (e) => {
            if (navigator.vibrate) navigator.vibrate([200]);
            entry(false, e instanceof ApiError ? e.message : "Could not record the scan.");
          },
        },
      );
    },
    [direction, storeId, scan],
  );

  useEffect(() => {
    if (!camera) inputRef.current?.focus();
  }, [camera, log.length]);

  return (
    <div className="grid gap-5 lg:grid-cols-[minmax(0,26rem)_1fr]">
      <div className="flex flex-col gap-4 rounded-xl border border-surface-border bg-surface p-4 shadow-card">
        <SegmentedControl
          label="Direction"
          value={direction}
          onChange={setDirection}
          options={[
            { value: "IN", label: "IN — arriving at store" },
            { value: "OUT", label: "OUT — leaving store" },
          ]}
        />
        <Select
          label={direction === "IN" ? "Store" : "Store (optional)"}
          value={storeId}
          searchable
          onChange={(e) => setStoreId(e.target.value)}
          options={[
            { value: "", label: direction === "IN" ? "Choose a store…" : "Where the bottle is" },
            ...(stores ?? []).map((s) => ({ value: s.id, label: `${s.name} (${s.code})` })),
          ]}
        />
        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (!needStore) {
              submit(text);
              setText("");
            }
          }}
          className="flex items-end gap-2"
        >
          <div className="flex-1">
            <Input ref={inputRef} label="Code" value={text} onChange={(e) => setText(e.target.value)} placeholder="Scan or type VK-XXXX-XXXX" autoComplete="off" autoCapitalize="characters" spellCheck={false} />
          </div>
          <Button type="submit" disabled={needStore || !text.trim()} isLoading={scan.isPending}>
            Record
          </Button>
        </form>
        {needStore && <p className="text-xs text-status-warning">Choose the store first.</p>}
        <Button variant="secondary" disabled={needStore} onClick={() => setCamera((c) => !c)}>
          {camera ? "Close camera" : "Scan with camera"}
        </Button>
        {camera && !needStore && <CameraScanner onCode={submit} />}
        <p className="text-xs text-gray-500">A USB / Bluetooth scanner gun works too — it types the code and presses Enter. OUT without a store uses the store the bottle is at.</p>
      </div>

      <div className="flex flex-col gap-2">
        {log.length === 0 && <p className="rounded-xl border border-dashed border-surface-border p-8 text-center text-sm text-gray-500">Scanned bottles appear here.</p>}
        {log.map((e) => (
          <div key={e.key} className={`flex flex-wrap items-center gap-3 rounded-xl border bg-surface px-4 py-3 ${e.ok ? (e.warning ? "border-status-warning" : "border-surface-border") : "border-status-danger"}`}>
            <Badge tone={e.ok ? (e.direction === "IN" ? "info" : "success") : "danger"}>{e.ok ? e.direction : "Failed"}</Badge>
            <span className="font-mono font-semibold text-gray-900">{e.serial}</span>
            <span className="text-sm text-gray-600">
              {e.message}
              {e.store ? ` · ${e.store}` : ""}
            </span>
            {e.warning && <span className="w-full text-xs font-medium text-status-warning">⚠ {e.warning}</span>}
          </div>
        ))}
      </div>
    </div>
  );
}

function CameraScanner({ onCode }: { onCode: (code: string) => void }) {
  const video = useRef<HTMLVideoElement>(null);
  const [error, setError] = useState<string | null>(null);
  const onCodeRef = useRef(onCode);
  useEffect(() => {
    onCodeRef.current = onCode;
  }, [onCode]);

  useEffect(() => {
    if (!window.BarcodeDetector) return;
    const detector = new window.BarcodeDetector({ formats: ["qr_code"] });
    let stream: MediaStream | undefined;
    let stopped = false;
    let last = { code: "", at: 0 };
    (async () => {
      try {
        stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" } });
        if (stopped || !video.current) {
          stream.getTracks().forEach((t) => t.stop());
          return;
        }
        video.current.srcObject = stream;
        await video.current.play();
        const tick = async () => {
          if (stopped || !video.current) return;
          try {
            const found = await detector.detect(video.current);
            const code = found[0]?.rawValue;
            // The same QR stays in view for a while: count it once every 4 seconds at most.
            if (code && (code !== last.code || Date.now() - last.at > 4000)) {
              last = { code, at: Date.now() };
              onCodeRef.current(code);
            }
          } catch {
            /* a frame that can't be read is fine */
          }
          setTimeout(tick, 250);
        };
        tick();
      } catch {
        setError("Camera access was blocked. Allow the camera for this site, or type the code.");
      }
    })();
    return () => {
      stopped = true;
      stream?.getTracks().forEach((t) => t.stop());
    };
  }, []);

  if (!window.BarcodeDetector) {
    return <p className="text-sm text-status-danger">This browser can&apos;t read QR codes with the camera. Use Chrome on Android, or type / scan with a scanner gun.</p>;
  }
  if (error) return <p className="text-sm text-status-danger">{error}</p>;
  return <video ref={video} playsInline muted className="aspect-square w-full rounded-xl bg-black object-cover" />;
}
