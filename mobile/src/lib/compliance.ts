/**
 * Pure rules for the Cards and Compliance screens (no React or native imports, so they are unit-tested with node).
 * The server is the authority for every rule here: it enforces them again and shrinks photos itself. The phone only
 * warns early and sends a smaller photo.
 */

export type DocKind = "card" | "bill" | "payment";
export type ComplianceStatus = "PENDING" | "PARTIAL" | "COMPLETE";
export type Tone = "success" | "warning" | "danger" | "info" | "neutral";

export const KINDS: DocKind[] = ["card", "bill", "payment"];
export const KIND_LABEL: Record<DocKind, string> = { card: "Card", bill: "Invoice", payment: "Payment proof" };
export const KIND_UPLOAD: Record<DocKind, string> = { card: "Upload card photo", bill: "Upload invoice", payment: "Upload payment proof" };

/** The upload limits as GET /uploads/policy reports them; these are the server's defaults, used until it answers. */
export interface UploadPolicy {
  photo_max_stored_kb: number;
  photo_max_upload_mb: number;
  pdf_max_mb: number;
  max_dimension: number;
  jpeg_quality: number;
  keep_below_kb: number;
}
export const DEFAULT_POLICY: UploadPolicy = {
  photo_max_stored_kb: 1024, photo_max_upload_mb: 12, pdf_max_mb: 2, max_dimension: 1600, jpeg_quality: 80, keep_below_kb: 350,
};

export const MAX_FILES = 20;
const PHOTO_TYPES = /^image\/(jpeg|png|webp)$/;

export interface SelectedFile {
  name: string;
  type: string;
  /** Bytes, when the phone told us (some pickers do not). */
  size?: number;
}

export const isPdf = (f: { type: string; name: string }) => f.type === "application/pdf" || /\.pdf$/i.test(f.name);
export const isPhoto = (f: { type: string; name: string }) => PHOTO_TYPES.test(f.type) || /\.(jpe?g|png|webp)$/i.test(f.name);

export function fmtBytes(n: number): string {
  return n < 1024 * 1024 ? `${Math.max(1, Math.round(n / 1024))} KB` : `${(n / 1024 / 1024).toFixed(1)} MB`;
}

/**
 * The same rules the server applies to a selection of files for one slot, so a person is told BEFORE sending:
 * photos or one PDF, at most 20 files, a PDF on its own and within its size limit, a photo within the incoming ceiling.
 * Returns the message to show, or null when the selection can be sent.
 */
export function validateSelection(files: SelectedFile[], policy: UploadPolicy = DEFAULT_POLICY): string | null {
  if (files.length > MAX_FILES) return `Choose at most ${MAX_FILES} files at once.`;
  for (const f of files) {
    if (!isPdf(f) && !isPhoto(f)) return `“${f.name}” must be a JPG, PNG or WEBP photo, or a PDF.`;
    if (isPdf(f) && f.size !== undefined && f.size > policy.pdf_max_mb * 1024 * 1024) {
      return `“${f.name}” is a PDF of ${fmtBytes(f.size)}. A PDF can be at most ${policy.pdf_max_mb} MB. Make it smaller, or take photos of the pages instead (photos are shrunk automatically).`;
    }
    if (isPhoto(f) && f.size !== undefined && f.size > policy.photo_max_upload_mb * 1024 * 1024) {
      return `“${f.name}” is ${fmtBytes(f.size)}, more than the ${policy.photo_max_upload_mb} MB allowed. Take the photo again at a lower quality.`;
    }
  }
  if (files.some(isPdf) && files.length > 1) return "A PDF must be uploaded on its own. Remove the other files.";
  return null;
}

/** What will happen to the selection on the server, in words. */
export function describeSelection(files: SelectedFile[]): string {
  if (files.length === 0) return "Nothing chosen yet";
  if (files.some(isPdf)) return "1 PDF (saved exactly as it is)";
  if (files.length === 1) return "1 photo";
  return `${files.length} photos (they will be merged into one PDF)`;
}

/** Whether a photo is worth shrinking on the phone: an unknown size is shrunk, a small one is left alone. */
export function shouldShrink(f: SelectedFile, policy: UploadPolicy = DEFAULT_POLICY): boolean {
  if (!isPhoto(f)) return false;
  return f.size === undefined || f.size > policy.keep_below_kb * 1024;
}

/** The size to resize to: the longest side limited to `max`, never enlarged, aspect ratio kept. */
export function fitWithin(width: number, height: number, max: number): { width: number; height: number } {
  const scale = Math.min(1, max / Math.max(width, height));
  return { width: Math.max(1, Math.round(width * scale)), height: Math.max(1, Math.round(height * scale)) };
}

export function monthLabel(ym: string, long = true): string {
  const [y, m] = ym.split("-").map(Number);
  if (!y || !m) return ym;
  return new Date(Date.UTC(y, m - 1, 1)).toLocaleDateString("en-IN", { month: long ? "long" : "short", year: "numeric", timeZone: "UTC" });
}

export const STATUS_LABEL: Record<ComplianceStatus, string> = { PENDING: "Nothing logged", PARTIAL: "Partly done", COMPLETE: "Complete" };
export const STATUS_TONE: Record<ComplianceStatus, Tone> = { PENDING: "danger", PARTIAL: "warning", COMPLETE: "success" };

export interface SlotDoc {
  status?: string | null;
  overdue?: boolean;
}

/** The badge for one slot, with the same wording as the web page (Add / On file / Paid / Pending / Overdue / Cleared). */
export function slotBadge(kind: DocKind, doc: SlotDoc | null): { text: string; tone: Tone } {
  if (!doc) return { text: "Missing", tone: "neutral" };
  if (kind === "bill") {
    if (doc.status === "CLEARED") return { text: "Cleared", tone: "success" };
    return doc.overdue ? { text: "Overdue", tone: "danger" } : { text: "Pending", tone: "warning" };
  }
  return { text: kind === "payment" ? "Paid" : "On file", tone: "success" };
}

/** How the logged slots read in a list row: "Card ✓  Invoice –  Payment ✓". */
export function logged(row: { card: unknown | null; bill: unknown | null; payment: unknown | null }): Record<DocKind, boolean> {
  return { card: !!row.card, bill: !!row.bill, payment: !!row.payment };
}

/** A key that only changes when the chosen files change: a retry of the same selection reuses it, so the server never stores it twice. */
export function selectionSignature(files: { uri: string }[]): string {
  return files.map((f) => f.uri).join("|");
}
