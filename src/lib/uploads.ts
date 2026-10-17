import { useQuery } from "@tanstack/react-query";
import { apiRequest } from "@/services/api";
import { camelize } from "@/lib/camel";

/**
 * The upload rules. The SERVER is the authority: it enforces every one of these again and shrinks photos itself.
 * The browser reads them from GET /uploads/policy so it can warn early and send a small photo instead of a 5 MB one.
 */
export interface UploadPolicy {
  photoMaxStoredKb: number;   // a stored photo is never larger than this
  photoMaxUploadMb: number;   // the largest raw file the server accepts
  pdfMaxMb: number;           // a PDF is stored as it is, so this is a hard limit
  maxDimension: number;       // longest side of a stored photo, in pixels
  jpegQuality: number;        // 1-100
  keepBelowKb: number;        // a photo this small is sent as it is
}

/** Used until the server answers (or if it can't): the same numbers the server defaults to. */
export const DEFAULT_POLICY: UploadPolicy = {
  photoMaxStoredKb: 1024, photoMaxUploadMb: 12, pdfMaxMb: 2, maxDimension: 1600, jpegQuality: 80, keepBelowKb: 350,
};

export function useUploadPolicy(): UploadPolicy {
  const q = useQuery({
    queryKey: ["upload-policy"],
    queryFn: async () => camelize<UploadPolicy>(await apiRequest("/uploads/policy", { silent: true })),
    staleTime: 10 * 60_000,
    retry: false,
  });
  return q.data ?? DEFAULT_POLICY;
}

/** A file the person must fix; the message is shown to them as it is. */
export class UploadRejected extends Error {}

export type Compress = (file: File, policy: UploadPolicy) => Promise<File>;

export const isPdfFile = (f: File) => f.type === "application/pdf" || /\.pdf$/i.test(f.name);
export const isPhotoFile = (f: File) => /^image\/(jpeg|png|webp)$/.test(f.type) || /\.(jpe?g|png|webp)$/i.test(f.name);

const mb = (bytes: number) => (bytes / 1024 / 1024).toFixed(1);

/** Short text for under an upload box. */
export function policyHint(p: UploadPolicy): string {
  return `photos are shrunk automatically · PDFs up to ${p.pdfMaxMb} MB`;
}

/**
 * Checks one file against the policy and returns what should be uploaded: a PDF untouched, a small photo untouched,
 * a large photo shrunk. Throws UploadRejected with a clear message for a file that cannot be accepted.
 * Never makes a file bigger and never touches a PDF.
 */
export async function prepareUpload(file: File, policy: UploadPolicy, compress: Compress = compressImage): Promise<File> {
  if (isPdfFile(file)) {
    if (file.size > policy.pdfMaxMb * 1024 * 1024) {
      throw new UploadRejected(
        `“${file.name}” is a PDF of ${mb(file.size)} MB. PDFs can be at most ${policy.pdfMaxMb} MB. Make the PDF smaller, or upload photos of the pages instead (photos are shrunk automatically).`,
      );
    }
    return file;
  }
  if (!isPhotoFile(file)) throw new UploadRejected(`“${file.name}” must be a JPG, PNG or WEBP photo, or a PDF.`);
  if (file.size > policy.photoMaxUploadMb * 1024 * 1024) {
    throw new UploadRejected(`“${file.name}” is ${mb(file.size)} MB, more than the ${policy.photoMaxUploadMb} MB the server accepts. Take the photo again at a lower quality.`);
  }
  if (file.size <= policy.keepBelowKb * 1024) return file;          // already small: never compressed twice
  let shrunk: File;
  try {
    shrunk = await compress(file, policy);
  } catch {
    return file;                                                    // the server shrinks it anyway
  }
  return shrunk.size < file.size ? shrunk : file;
}

/** Prepares several files; the ones that cannot be accepted come back as messages instead of stopping the rest. */
export async function prepareMany(files: File[], policy: UploadPolicy, compress: Compress = compressImage): Promise<{ ok: File[]; problems: string[] }> {
  const ok: File[] = [];
  const problems: string[] = [];
  for (const f of files) {
    try {
      ok.push(await prepareUpload(f, policy, compress));
    } catch (e) {
      problems.push(e instanceof Error ? e.message : `“${f.name}” could not be used.`);
    }
  }
  return { ok, problems };
}

/**
 * Browser-side shrink: upright (EXIF orientation applied by the browser), limited to maxDimension, re-encoded as JPEG
 * with a lower quality, then a smaller size, until it fits the stored-size limit. Needs no library.
 */
export const compressImage: Compress = async (file, policy) => {
  if (typeof createImageBitmap !== "function" || typeof document === "undefined") return file;
  const bitmap = await createImageBitmap(file, { imageOrientation: "from-image" });
  try {
    const limit = policy.photoMaxStoredKb * 1024;
    let dim = policy.maxDimension;
    let quality = policy.jpegQuality / 100;
    for (;;) {
      const scale = Math.min(1, dim / Math.max(bitmap.width, bitmap.height));
      const canvas = document.createElement("canvas");
      canvas.width = Math.max(1, Math.round(bitmap.width * scale));
      canvas.height = Math.max(1, Math.round(bitmap.height * scale));
      const ctx = canvas.getContext("2d");
      if (!ctx) return file;
      ctx.fillStyle = "#ffffff";                                    // a transparent PNG becomes a JPEG on white
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      ctx.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
      const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, "image/jpeg", quality));
      if (!blob) return file;
      if (blob.size <= limit) return new File([blob], file.name.replace(/\.\w+$/, "") + ".jpg", { type: "image/jpeg", lastModified: Date.now() });
      if (quality > 0.55) quality = Math.max(0.55, quality - 0.08);
      else if (dim > 900) dim = Math.round(dim * 0.85);
      else return file;                                             // cannot fit: the server will say so clearly
    }
  } finally {
    bitmap.close();
  }
};
