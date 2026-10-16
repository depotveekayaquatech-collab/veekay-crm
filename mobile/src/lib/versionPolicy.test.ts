import test from "node:test";
import assert from "node:assert/strict";
import { apkUpdateState, parseManifest, parseVersionCode } from "./versionPolicy.ts";

const manifest = (over: Record<string, unknown> = {}) => ({
  android: { latestVersionCode: 8, latestVersionName: "1.0.1", minVersionCode: 0, downloadUrl: "https://example.com/a.apk", notes: "n", ...over },
});

test("an installed build below the latest gets an optional update; at or above gets none", () => {
  const m = parseManifest(manifest());
  assert.equal(apkUpdateState(7, m), "optional");
  assert.equal(apkUpdateState(8, m), "none");
  assert.equal(apkUpdateState(9, m), "none");
});

test("version codes compare as numbers, not text", () => {
  const m = parseManifest(manifest({ latestVersionCode: 10 }));
  assert.equal(apkUpdateState(9, m), "optional");   // "9" > "10" as text would wrongly say up to date
  assert.equal(parseVersionCode("10"), 10);
  assert.equal(parseVersionCode(null), 0);
});

test("below the minimum is required; never required or optional without a usable https link", () => {
  assert.equal(apkUpdateState(6, parseManifest(manifest({ minVersionCode: 7 }))), "required");
  assert.equal(apkUpdateState(6, parseManifest(manifest({ downloadUrl: "" }))), "none");
  assert.equal(apkUpdateState(6, parseManifest(manifest({ downloadUrl: "http://example.com/a.apk" }))), "none");
});

test("a malformed or missing manifest never blocks anyone", () => {
  assert.equal(parseManifest(null), null);
  assert.equal(parseManifest({ android: { latestVersionCode: "x" } }), null);
  assert.equal(apkUpdateState(5, null), "none");
  assert.equal(apkUpdateState(0, parseManifest(manifest())), "none");
});

test("the recorded APK size is read when valid and ignored when not", () => {
  assert.equal(parseManifest(manifest({ apkSizeBytes: 56326237 }))!.apkSizeBytes, 56326237);
  assert.equal(parseManifest(manifest({ apkSizeBytes: "oops" }))!.apkSizeBytes, 0);
});
