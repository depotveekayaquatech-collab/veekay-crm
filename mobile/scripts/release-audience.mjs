/**
 * Who gets a release: everyone, only Veekay employees, or only vendors / POCs. Pure helpers (no file or network access), so they
 * are unit-tested. The update file is { android: { ...shared rules, staff: {...}, partner: {...} } }; the app reads it with the
 * same rules (src/lib/versionPolicy.ts).
 */

export const AUDIENCES = ["both", "staff", "partner"];

const isObject = (v) => !!v && typeof v === "object" && !Array.isArray(v);

/** The release one audience is offered now, laid out the way the app reads it: its own section if that has a newest build, else the shared one. */
export function entryFor(manifest, audience) {
  const base = manifest?.android;
  if (!isObject(base)) return null;
  const over = audience === "staff" || audience === "partner" ? base[audience] : undefined;
  if (isObject(over) && over.latestVersionCode !== undefined) return over;
  if (isObject(over) && over.minVersionCode !== undefined) return { ...base, minVersionCode: over.minVersionCode };
  return base;
}

/** The highest build any audience is offered. */
export function newestCode(manifest) {
  return Math.max(0, ...AUDIENCES.map((a) => Number(entryFor(manifest, a)?.latestVersionCode) || 0));
}

/** The minimum build that already applies to the audience. A release keeps it unless you say otherwise, so nobody is newly forced. */
export function currentMinCode(manifest, audience) {
  return Number(entryFor(manifest, audience)?.minVersionCode) || 0;
}

/** Every download link the file still points at (those APK files must stay hosted). */
export function linksInUse(manifest) {
  return new Set(AUDIENCES.map((a) => entryFor(manifest, a)?.downloadUrl).filter(Boolean));
}

/** One release's fields. Throws a readable Error for anything unsafe. */
export function releaseEntry({ code, name, url, notes = "", minCode = 0, sizeBytes, sha256 }) {
  if (!Number.isInteger(code) || code < 1) throw new Error(`Bad version code: ${code}`);
  if (!/^https:\/\/[^\s]+$/.test(url ?? "")) throw new Error("The download link must be an https:// address.");
  if (!Number.isInteger(minCode) || minCode < 0 || minCode > code) throw new Error(`minVersionCode must be between 0 and ${code}.`);
  if (!name) throw new Error("Missing version name.");
  return {
    latestVersionCode: code,
    latestVersionName: name,
    minVersionCode: minCode,
    downloadUrl: url,
    notes: String(notes).slice(0, 300),
    ...(sizeBytes ? { apkSizeBytes: sizeBytes } : {}),
    ...(sha256 ? { apkSha256: sha256 } : {}),
  };
}

/**
 * The new update file after publishing `entry` to an audience.
 *   both            - everyone follows it (the shared rules); any per-audience sections are cleared.
 *   staff / partner - only that audience gets it, in its own section; the shared rules and the other audience stay as they are.
 * A build that is not higher than what the audience already has is refused (phones would not see an update).
 */
export function applyRelease(existing, entry, audience = "both", { force = false } = {}) {
  if (!AUDIENCES.includes(audience)) throw new Error(`audience must be one of ${AUDIENCES.join(", ")}.`);
  const previous = audience === "both" ? newestCode(existing) : Number(entryFor(existing, audience)?.latestVersionCode) || 0;
  if (!force && entry.latestVersionCode <= previous) {
    throw new Error(
      `Version code ${entry.latestVersionCode} is not higher than the one already published for ${audience === "both" ? "everyone" : audience} (${previous}). Phones would not see it as an update.`,
    );
  }
  if (audience === "both") return { android: entry };
  if (!isObject(existing?.android)) {
    throw new Error("Publish a release for everyone first (--audience both): phones need it before they can read separate employee / vendor rules.");
  }
  return { android: { ...existing.android, [audience]: entry } };
}
