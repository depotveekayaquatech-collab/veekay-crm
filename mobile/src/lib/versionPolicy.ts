/**
 * Pure rules for "does this installed APK need replacing?". No React / native imports, so they are easy to test.
 *
 * Versions are compared as NUMBERS (Android versionCode), never as strings: 10 > 9 numerically but not alphabetically.
 * The installed versionCode comes from the binary itself (expo-application `nativeBuildVersion`), not from JS that an
 * over-the-air update may have replaced.
 *
 * One app serves two kinds of people, so the update file can give each its own rules:
 *   { "android": { ...rules everyone follows (and builds that predate this feature),
 *                  "staff":   { ...only what differs for Veekay employees },
 *                  "partner": { ...only what differs for vendors / POCs } } }
 * A person signed in as `staff` or `partner` gets the shared rules with that section laid over them. Before anyone is
 * signed in (and for old builds) only the shared rules apply.
 */
export type Audience = "staff" | "partner";

export type ApkManifest = {
  latestVersionCode: number;
  latestVersionName: string;
  /** Installed builds below this must update before the app can be used. */
  minVersionCode: number;
  /** https link to the newest APK (a GitHub release asset, a Drive/S3 link, an EAS build page, ...). */
  downloadUrl: string;
  notes: string;
  /** Size of the APK in bytes when the release script recorded it (0 = unknown). Used to reject a truncated download. */
  apkSizeBytes: number;
};

export type ApkUpdateState = "none" | "optional" | "required";

type Entry = Record<string, unknown>;
const FIELDS = ["latestVersionCode", "latestVersionName", "minVersionCode", "downloadUrl", "notes", "apkSizeBytes", "apkSha256"] as const;

const isObject = (v: unknown): v is Entry => !!v && typeof v === "object" && !Array.isArray(v);

/**
 * The shared rules with one audience's section on top. A section that sets a newest build replaces the whole release (its
 * build, link, size and notes belong together); a section with no `latestVersionCode` may only change the minimum.
 */
function layered(android: Entry, audience: Audience | null | undefined): Entry {
  const over = audience ? android[audience] : undefined;
  if (!isObject(over)) return android;
  if (over.latestVersionCode !== undefined) {
    const own: Entry = {};
    for (const f of FIELDS) if (over[f] !== undefined) own[f] = over[f];
    return own;
  }
  return over.minVersionCode !== undefined ? { ...android, minVersionCode: over.minVersionCode } : android;
}

/** Reads the hosted `app-update.json`. Anything malformed returns null, which means "no update info": the app carries on. */
export function parseManifest(json: unknown, audience?: Audience | null): ApkManifest | null {
  const base = isObject(json) && isObject(json.android) ? json.android : null;
  if (!base) return null;
  const a = layered(base, audience);
  const latest = Number(a.latestVersionCode);
  const min = Number(a.minVersionCode ?? 0);
  const url = typeof a.downloadUrl === "string" ? a.downloadUrl.trim() : "";
  if (!Number.isInteger(latest) || latest < 1 || !Number.isInteger(min) || min < 0) return null;
  return {
    latestVersionCode: latest,
    latestVersionName: typeof a.latestVersionName === "string" ? a.latestVersionName : String(latest),
    minVersionCode: min,
    downloadUrl: url.startsWith("https://") ? url : "", // only https links are ever opened
    notes: typeof a.notes === "string" ? a.notes : "",
    apkSizeBytes: Number.isInteger(Number(a.apkSizeBytes)) && Number(a.apkSizeBytes) > 0 ? Number(a.apkSizeBytes) : 0,
  };
}

export function parseVersionCode(raw: string | null | undefined): number {
  const n = Number.parseInt(String(raw ?? ""), 10);
  return Number.isFinite(n) ? n : 0;
}

/** required: below the minimum. optional: below the latest. A manifest with no usable link never blocks anyone. */
export function apkUpdateState(installedCode: number, m: ApkManifest | null): ApkUpdateState {
  if (!m || installedCode <= 0) return "none";
  if (installedCode < m.minVersionCode && m.downloadUrl) return "required";
  if (installedCode < m.latestVersionCode && m.downloadUrl) return "optional";
  return "none";
}
