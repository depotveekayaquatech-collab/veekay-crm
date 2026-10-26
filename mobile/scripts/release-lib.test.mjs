import test from "node:test";
import assert from "node:assert/strict";
import { buildManifest, codeFromFileName, defaultMinCode, looksLikeApk, nextVersionCode } from "./release-lib.mjs";

test("version code comes from the file name and the next one is above everything built or published", () => {
  assert.equal(codeFromFileName("Aquatrack-1.0.1-code8.apk"), 8);
  assert.equal(codeFromFileName("readme.txt"), 0);
  assert.equal(nextVersionCode([6, 7], 0), 8);
  assert.equal(nextVersionCode([], 9), 10);   // the manifest may be ahead of what is on disk
  assert.equal(nextVersionCode([], 0), 1);
});

test("a download page is not an APK", () => {
  assert.equal(looksLikeApk(Uint8Array.from([0x50, 0x4b, 0x03, 0x04, 1])), true);
  assert.equal(looksLikeApk(new TextEncoder().encode("<!DOCTYPE html>")), false);
  assert.equal(looksLikeApk(new Uint8Array(2)), false);
});

test("manifest: refuses an unsafe or non-upgrading release", () => {
  const ok = { code: 8, name: "1.0.1", url: "https://example.com/a.apk", previousLatest: 7 };
  const m = buildManifest({ ...ok, sizeBytes: 123, notes: "n" });
  assert.equal(m.android.latestVersionCode, 8);
  assert.equal(m.android.apkSizeBytes, 123);
  assert.equal(m.android.minVersionCode, 0);
  assert.throws(() => buildManifest({ ...ok, code: 7 }), /not higher/);
  assert.throws(() => buildManifest({ ...ok, url: "http://example.com/a.apk" }), /https/);
  assert.throws(() => buildManifest({ ...ok, minCode: 9 }), /minVersionCode/);
  assert.equal(buildManifest({ ...ok, code: 7, force: true }).android.latestVersionCode, 7);
});

test("a phone may be one release behind; two behind must update", () => {
  assert.equal(defaultMinCode(9, 8), 8);   // releasing 9 after 8: phones on 8 keep working, 7 and older are blocked
  assert.equal(defaultMinCode(10, 9), 9);  // releasing 10: now 8 is two behind and blocked
  assert.equal(defaultMinCode(1, 0), 0);   // the first release blocks nobody
  assert.equal(defaultMinCode(5, 5), 0);   // never a minimum above or equal to the release itself (a forced re-release)
});
