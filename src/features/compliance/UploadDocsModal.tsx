import { useRef, useState, type DragEvent } from "react";
import { Modal } from "@/components/ui/Modal";
import { Button } from "@/components/ui/Button";
import { IconClose } from "@/components/ui/icons";
import { DOC_LABEL, useUploadDoc, type DocKind } from "@/features/compliance/api";

const MAX_MB = 12;
const MAX_FILES = 20;
const ACCEPT = "image/jpeg,image/png,image/webp,application/pdf,.jpg,.jpeg,.png,.webp,.pdf";

function isPdf(f: File) {
  return f.type === "application/pdf" || /\.pdf$/i.test(f.name);
}
function isImage(f: File) {
  return /^image\/(jpeg|png|webp)$/.test(f.type) || /\.(jpe?g|png|webp)$/i.test(f.name);
}
const size = (b: number) => (b < 1024 * 1024 ? `${Math.max(1, Math.round(b / 1024))} KB` : `${(b / 1024 / 1024).toFixed(1)} MB`);

/** Validation that mirrors the server rules, so people get instant feedback. */
function validate(files: File[]): string | null {
  if (files.length > MAX_FILES) return `Choose at most ${MAX_FILES} files.`;
  for (const f of files) {
    if (!isPdf(f) && !isImage(f)) return `“${f.name}” must be a JPG, PNG or WEBP photo, or a PDF.`;
    if (f.size > MAX_MB * 1024 * 1024) return `“${f.name}” is larger than ${MAX_MB} MB.`;
  }
  if (files.some(isPdf) && files.length > 1) return "A PDF must be uploaded on its own — remove the other files.";
  return null;
}

export function UploadDocsModal({
  storeId,
  storeName,
  month,
  monthLabel,
  kind,
  replacing,
  onClose,
}: {
  storeId: string;
  storeName: string;
  month: string;
  monthLabel: string;
  kind: DocKind;
  replacing: boolean;
  onClose: () => void;
}) {
  const upload = useUploadDoc();
  const inputRef = useRef<HTMLInputElement>(null);
  const [files, setFiles] = useState<File[]>([]);
  const [dragging, setDragging] = useState(false);

  const error = validate(files);
  const label = DOC_LABEL[kind];

  function add(list: FileList | null | undefined) {
    if (!list?.length) return;
    setFiles((prev) => [...prev, ...Array.from(list)]);
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
      title={`${replacing ? "Upload new" : "Upload"} ${label}`}
      description={`${storeName} · ${monthLabel}`}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
          <Button
            disabled={files.length === 0 || error !== null}
            isLoading={upload.isPending}
            onClick={() => upload.mutate({ storeId, month, kind, files }, { onSuccess: onClose })}
          >
            {files.length > 1 ? `Merge ${files.length} pages & upload` : "Upload"}
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-4">
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
            accept={ACCEPT}
            multiple
            className="hidden"
            onChange={(e) => {
              add(e.target.files);
              e.target.value = ""; // allow picking the same file again
            }}
          />
          <p className="text-sm font-semibold text-gray-800">Drop photos or a PDF here, or click to browse</p>
          <p className="text-xs text-gray-500">On a phone this opens the camera or gallery</p>
        </div>

        {files.length > 0 && (
          <ul className="flex flex-col divide-y divide-surface-border rounded-lg border border-surface-border">
            {files.map((f, i) => (
              <li key={`${f.name}-${i}`} className="flex items-center gap-3 px-3 py-2 text-sm">
                <span className="min-w-0 flex-1 truncate font-medium text-gray-800">{f.name}</span>
                <span className="shrink-0 text-xs text-gray-500">{size(f.size)}</span>
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
        )}

        {error && (
          <p role="alert" className="rounded-lg bg-status-danger-soft px-3 py-2 text-sm text-status-danger">{error}</p>
        )}
        {upload.error && !error && (
          <p role="alert" className="rounded-lg bg-status-danger-soft px-3 py-2 text-sm text-status-danger">
            {upload.error instanceof Error ? upload.error.message : "Upload failed."}
          </p>
        )}

        <ul className="list-disc space-y-0.5 rounded-lg bg-surface-subtle px-4 py-3 pl-8 text-xs text-gray-600">
          <li>One file is saved as it is.</li>
          <li>Two or more photos are merged into a single PDF.</li>
          <li>A PDF must be uploaded on its own.</li>
          <li>Up to {MAX_MB} MB per file.{replacing ? " This becomes the current file; the earlier one is kept in history." : ""}</li>
          {kind === "bill" && <li>The invoice is due 45 days after the month ends.</li>}
        </ul>
      </div>
    </Modal>
  );
}
