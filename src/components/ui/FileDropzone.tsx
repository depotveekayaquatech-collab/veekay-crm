import { useRef, useState, type DragEvent } from "react";

/** Drag-and-drop / click-to-browse file picker. Validation happens in the parent via `onPick`. */
export function FileDropzone({
  file,
  onPick,
  accept,
  hint,
}: {
  file: File | null;
  onPick: (file: File | undefined) => void;
  accept: string;
  hint: string;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);

  function onDrop(e: DragEvent) {
    e.preventDefault();
    setDragging(false);
    onPick(e.dataTransfer.files?.[0]);
  }

  const size = file ? (file.size < 1024 * 1024 ? `${Math.max(1, Math.round(file.size / 1024))} KB` : `${(file.size / 1024 / 1024).toFixed(1)} MB`) : "";

  return (
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
      className={`flex cursor-pointer flex-col items-center justify-center gap-1.5 rounded-xl border-2 border-dashed px-4 py-9 text-center transition-colors ${
        dragging
          ? "border-brand-500 bg-brand-50"
          : file
            ? "border-aqua-400 bg-aqua-50"
            : "border-surface-border bg-surface-subtle hover:border-brand-300 hover:bg-brand-50/50"
      }`}
    >
      <input ref={inputRef} type="file" accept={accept} className="hidden" onChange={(e) => onPick(e.target.files?.[0])} />
      {file ? (
        <>
          <p className="text-sm font-bold text-heading">{file.name}</p>
          <p className="text-xs text-gray-500">{size} · click to choose a different file</p>
        </>
      ) : (
        <>
          <p className="text-sm font-semibold text-gray-800">Drop a file here, or click to browse</p>
          <p className="text-xs text-gray-500">{hint}</p>
        </>
      )}
    </div>
  );
}
