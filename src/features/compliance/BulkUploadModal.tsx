import { useRef, useState, type DragEvent } from "react";
import { Modal } from "@/components/ui/Modal";
import { Button } from "@/components/ui/Button";
import { IconCheckCircle, IconClose } from "@/components/ui/icons";
import { DOC_LABEL, useBulkUpload, type BulkResult, type DocKind } from "@/features/compliance/api";
import { monthLabel } from "@/lib/months";

const MAX_FILES = 300;
const MAX_MB = 12;
const KINDS: DocKind[] = ["card", "bill", "payment"];
const OPTION_LABEL: Record<DocKind, string> = {
  card: "Compliance cards",
  bill: "Invoices",
  payment: "Payment proofs",
};
const field = "h-10 w-full rounded-lg border border-surface-border bg-white px-3 text-sm shadow-sm outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20";

/** Many files at once: each is matched to a store by the store code at the start of its file name. */
export function BulkUploadModal({ month, months, onClose }: { month: string; months: string[]; onClose: () => void }) {
  const bulk = useBulkUpload();
  const inputRef = useRef<HTMLInputElement>(null);
  const [m, setM] = useState(month);
  const [kind, setKind] = useState<DocKind>("card");
  const [files, setFiles] = useState<File[]>([]);
  const [dragging, setDragging] = useState(false);
  const [result, setResult] = useState<BulkResult | null>(null);

  const tooBig = files.find((f) => f.size > MAX_MB * 1024 * 1024);
  const error = files.length > MAX_FILES ? `Choose at most ${MAX_FILES} files at once.` : tooBig ? `“${tooBig.name}” is larger than ${MAX_MB} MB.` : null;

  function add(list: FileList | null | undefined) {
    if (list?.length) setFiles((prev) => [...prev, ...Array.from(list)]);
  }
  function onDrop(e: DragEvent) {
    e.preventDefault();
    setDragging(false);
    add(e.dataTransfer.files);
  }

  return (
    <Modal
      open
      onClose={onClose}
      title="Bulk upload"
      description="Upload many cards, invoices or payment proofs at once — files are matched to stores by the store code in the file name."
      footer={
        result ? (
          <Button onClick={onClose}>Done</Button>
        ) : (
          <>
            <Button variant="secondary" onClick={onClose}>Cancel</Button>
            <Button
              disabled={files.length === 0 || error !== null}
              isLoading={bulk.isPending}
              onClick={() => bulk.mutate({ month: m, kind, files }, { onSuccess: setResult })}
            >
              Upload {files.length > 0 ? `${files.length} file${files.length > 1 ? "s" : ""}` : ""}
            </Button>
          </>
        )
      }
    >
      {result ? (
        <div className="flex flex-col gap-4">
          <div className="flex items-center gap-3 rounded-xl bg-status-success-soft px-4 py-3 text-status-success">
            <IconCheckCircle className="h-6 w-6 shrink-0" />
            <div>
              <p className="text-sm font-bold">{result.storesUpdated} store{result.storesUpdated === 1 ? "" : "s"} updated</p>
              <p className="text-xs opacity-80">
                {result.filesMatched} of {result.filesReceived} files matched · {DOC_LABEL[result.kind]} · {monthLabel(result.month)}
              </p>
            </div>
          </div>
          {result.failed.length > 0 && (
            <div className="rounded-lg bg-status-danger-soft px-3 py-2.5 text-xs text-status-danger">
              <p className="font-bold">{result.failed.length} store{result.failed.length > 1 ? "s" : ""} couldn&apos;t be saved</p>
              <ul className="mt-1 max-h-32 list-disc space-y-0.5 overflow-auto pl-4">
                {result.failed.map((f, i) => (
                  <li key={i}>{f.store}: {f.error}</li>
                ))}
              </ul>
            </div>
          )}
          {result.unmatched.length > 0 && (
            <div className="rounded-lg bg-status-warning-soft px-3 py-2.5 text-xs text-status-warning">
              <p className="font-bold">{result.unmatched.length} file{result.unmatched.length > 1 ? "s" : ""} not matched to a store</p>
              <ul className="mt-1 max-h-36 list-disc space-y-0.5 overflow-auto pl-4">
                {result.unmatched.map((u, i) => (
                  <li key={i}>{u}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      ) : (
        <div className="flex flex-col gap-4">
          <div className="grid gap-3 sm:grid-cols-2">
            <label className="flex flex-col gap-1.5 text-[13px] font-semibold text-gray-700">
              Month
              <select className={field} value={m} onChange={(e) => setM(e.target.value)}>
                {months.map((x) => (
                  <option key={x} value={x}>{monthLabel(x)}</option>
                ))}
              </select>
            </label>
            <label className="flex flex-col gap-1.5 text-[13px] font-semibold text-gray-700">
              Document type
              <select className={field} value={kind} onChange={(e) => setKind(e.target.value as DocKind)}>
                {KINDS.map((k) => (
                  <option key={k} value={k}>{OPTION_LABEL[k]}</option>
                ))}
              </select>
            </label>
          </div>

          <div
            onDragOver={(e) => {
              e.preventDefault();
              setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={onDrop}
            onClick={() => inputRef.current?.click()}
            role="button"
            tabIndex={0}
            onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && inputRef.current?.click()}
            className={`flex cursor-pointer flex-col items-center gap-1.5 rounded-xl border-2 border-dashed px-4 py-8 text-center transition-colors ${
              dragging ? "border-brand-500 bg-brand-50" : "border-surface-border bg-surface-subtle hover:border-brand-300 hover:bg-brand-50/50"
            }`}
          >
            <input
              ref={inputRef}
              type="file"
              multiple
              accept="image/jpeg,image/png,image/webp,application/pdf,.jpg,.jpeg,.png,.webp,.pdf"
              className="hidden"
              onChange={(e) => {
                add(e.target.files);
                e.target.value = "";
              }}
            />
            <p className="text-sm font-semibold text-gray-800">Drop files here, or click to browse</p>
            <p className="text-xs text-gray-500">JPG, PNG, WEBP or PDF · up to {MAX_MB} MB each · {MAX_FILES} files at a time</p>
          </div>

          {files.length > 0 && (
            <div className="rounded-lg border border-surface-border">
              <div className="flex items-center justify-between border-b border-surface-border px-3 py-2 text-xs text-gray-500">
                <span>{files.length} file{files.length > 1 ? "s" : ""} selected</span>
                <button className="font-semibold text-brand-600 hover:text-brand-700" onClick={() => setFiles([])}>Clear all</button>
              </div>
              <ul className="max-h-40 divide-y divide-surface-border overflow-y-auto">
                {files.map((f, i) => (
                  <li key={`${f.name}-${i}`} className="flex items-center gap-3 px-3 py-1.5 text-sm">
                    <span className="min-w-0 flex-1 truncate text-gray-800">{f.name}</span>
                    <button
                      aria-label={`Remove ${f.name}`}
                      onClick={() => setFiles((prev) => prev.filter((_, j) => j !== i))}
                      className="rounded p-1 text-gray-400 hover:bg-surface-subtle hover:text-gray-700"
                    >
                      <IconClose className="h-4 w-4" />
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {error && <p role="alert" className="rounded-lg bg-status-danger-soft px-3 py-2 text-sm text-status-danger">{error}</p>}
          {bulk.error && !error && (
            <p role="alert" className="rounded-lg bg-status-danger-soft px-3 py-2 text-sm text-status-danger">
              {bulk.error instanceof Error ? bulk.error.message : "Upload failed."}
            </p>
          )}

          <ul className="list-disc space-y-0.5 rounded-lg bg-surface-subtle px-4 py-3 pl-8 text-xs text-gray-600">
            <li>
              Start each file name with the store code: <b>9451.pdf</b>, <b>9451_page2.jpg</b>, <b>AGR_DYLBGH_P01R0CC page 2.png</b>.
            </li>
            <li>Several photos for the same store are merged into one PDF, in file-name order.</li>
            <li>A PDF must be the only file for its store. Existing documents are replaced.</li>
          </ul>
        </div>
      )}
    </Modal>
  );
}
