import test from "node:test";
import assert from "node:assert/strict";
import { applyRelease, currentMinCode, entryFor, linksInUse, newestCode, releaseEntry } from "./release-audience.mjs";
import { apkUpdateState, parseManifest } from "../src/lib/versionPolicy.ts";

const entry = (code, over = {}) => releaseEntry({ code, name: "1.2.0", url: `https://example.com/v${code}.apk`, minCode: 18, sizeBytes: 100, ...over });
const published19 = { android: entry(19) };

test("a release for everyone replaces the shared rules and clears per-audience sections", () => {
  const staffOnly = applyRelease(published19, entry(21), "staff");
  const everyone = applyRelease(staffOnly, entry(22), "both");
  assert.deepEqual(Object.keys(everyone.android).includes("staff"), false);
  assert.equal(everyone.android.latestVersionCode, 22);
});

test("an employee-only release leaves vendors and POCs on their current build", () => {
  const m = applyRelease(published19, entry(20), "staff");
  assert.equal(entryFor(m, "staff").latestVersionCode, 20);
  assert.equal(entryFor(m, "partner").latestVersionCode, 19);
  assert.equal(entryFor(m, "both").latestVersionCode, 19);
  assert.equal(newestCode(m), 20);
  // what the app shows a phone on build 19: employees are offered 20, vendors / POCs and signed-out phones nothing
  assert.equal(apkUpdateState(19, parseManifest(m, "staff")), "optional");
  assert.equal(apkUpdateState(19, parseManifest(m, "partner")), "none");
  assert.equal(apkUpdateState(19, parseManifest(m, null)), "none");
  assert.equal(apkUpdateState(19, parseManifest(m)), "none");
});

test("a vendor / POC release is independent of the employee one", () => {
  const m = applyRelease(applyRelease(published19, entry(20), "staff"), entry(21), "partner");
  assert.equal(entryFor(m, "staff").latestVersionCode, 20);
  assert.equal(entryFor(m, "partner").latestVersionCode, 21);
  assert.equal(linksInUse(m).size, 3);   // all three APK files must stay hosted
});

test("a build is only forced on the audience it was published to", () => {
  const m = applyRelease(published19, entry(20, { minCode: 20 }), "staff");
  assert.equal(apkUpdateState(19, parseManifest(m, "staff")), "required");
  assert.equal(apkUpdateState(19, parseManifest(m, "partner")), "none");
});

test("a release keeps the minimum that already applies unless told otherwise", () => {
  const m = applyRelease(published19, entry(20), "staff");
  assert.equal(currentMinCode(published19, "staff"), 18);
  assert.equal(currentMinCode(m, "partner"), 18);
  assert.equal(currentMinCode(null, "both"), 0);
});

test("refuses a build that is not higher for that audience, and separate rules before an everyone release exists", () => {
  assert.throws(() => applyRelease(published19, entry(19), "both"), /not higher/);
  assert.throws(() => applyRelease(applyRelease(published19, entry(21), "staff"), entry(20), "staff"), /not higher/);
  assert.throws(() => applyRelease(null, entry(20), "staff"), /for everyone first/);
  assert.throws(() => applyRelease(published19, entry(20), "nobody"), /audience must be/);
  assert.equal(applyRelease(published19, entry(19), "both", { force: true }).android.latestVersionCode, 19);
});
