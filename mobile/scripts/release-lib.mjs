/** Pure helpers for the release scripts (no file or network access, so they are unit-tested). */

/** The version code of an APK file name such as Veekay-Partner-1.0.1-code8.apk, or 0. */
export function codeFromFileName(name) {
  const m = /-code(\d+)\.apk$/i.exec(name);
  return m ? Number(m[1]) : 0;
}

/** Next version code: always above every APK already built AND above what the published manifest announces. */
export function nextVersionCode(builtCodes, manifestLatest = 0) {
  return Math.max(0, manifestLatest, ...builtCodes) + 1;
}

/** An APK is a zip file: it starts with "PK\x03\x04". A download page or a login page does not. */
export function looksLikeApk(bytes) {
  return bytes.length >= 4 && bytes[0] === 0x50 && bytes[1] === 0x4b && bytes[2] === 0x03 && bytes[3] === 0x04;
}

/** The app-update.json content for a release. Throws a readable Error for anything unsafe. */
export function buildManifest({ code, name, url, notes = "", minCode = 0, sizeBytes, sha256, previousLatest = 0, force = false }) {
  if (!Number.isInteger(code) || code < 1) throw new Error(`Bad version code: ${code}`);
  if (!force && code <= previousLatest) {
    throw new Error(`Version code ${code} is not higher than the one already published (${previousLatest}). Phones would not see it as an update.`);
  }
  if (!/^https:\/\/[^\s]+$/.test(url ?? "")) throw new Error("The download link must be an https:// address.");
  if (!Number.isInteger(minCode) || minCode < 0 || minCode > code) throw new Error(`minVersionCode must be between 0 and ${code}.`);
  if (!name) throw new Error("Missing version name.");
  return {
    android: {
      latestVersionCode: code,
      latestVersionName: name,
      minVersionCode: minCode,
      downloadUrl: url,
      notes: String(notes).slice(0, 300),
      ...(sizeBytes ? { apkSizeBytes: sizeBytes } : {}),
      ...(sha256 ? { apkSha256: sha256 } : {}),
    },
  };
}
