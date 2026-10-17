/**
 * Check an app update from your PC, the way a phone would see it. Changes nothing.
 *
 *   npm run release:check                               the LIVE update file (https://veekay-crm.vercel.app/app-update.json)
 *   npm run release:check -- --manifest ../public/app-update.json      a local file, before you push it
 *   npm run release:check -- --installed 6,8,9          which build numbers to simulate (default: 5 up to the newest)
 *   npm run release:check -- --apk build/apk/Veekay-Partner-1.0.1-code9.apk   check a local APK file instead of downloading
 *   npm run release:check -- --no-download              only read the update file and test the link, skip the big download
 *
 * It reports: what the update file says; what each installed build would see (nothing / "update available" / "update
 * required"), using the SAME rules as the app (src/lib/versionPolicy.ts); that the download link serves a real APK of the
 * recorded size and SHA-256; and, with the Android SDK installed, the APK's real version code and signing certificate.
 * Exit code 0 = everything matches, 1 = a problem was found.
 */
import { createHash } from "node:crypto";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { apkUpdateState, parseManifest } from "../src/lib/versionPolicy.ts";

const LIVE = "https://veekay-crm.vercel.app/app-update.json";
const args = process.argv.slice(2);
const opt = (n) => { const i = args.indexOf(`--${n}`); return i >= 0 ? args[i + 1] : undefined; };
const flag = (n) => args.includes(`--${n}`);
const problems = [];
const ok = (m) => console.log(`  OK    ${m}`);
const bad = (m) => { problems.push(m); console.log(`  FAIL  ${m}`); };
const mb = (n) => `${(n / 1048576).toFixed(1)} MB`;

// ---- 1. the update file ------------------------------------------------------------------------------------------------
const source = opt("manifest") ?? LIVE;
console.log(`\nUpdate file: ${source}`);
let raw;
try {
  raw = /^https?:\/\//i.test(source)
    ? await (await fetch(source, { headers: { "Cache-Control": "no-cache" } })).text()
    : fs.readFileSync(path.resolve(source), "utf8");
} catch (e) {
  console.error(`  FAIL  could not read it: ${e.message}`);
  process.exit(1);
}
let json;
try { json = JSON.parse(raw); } catch { console.error("  FAIL  it is not valid JSON"); process.exit(1); }
const m = parseManifest(json);
if (!m) { console.error("  FAIL  the app would ignore this file (no usable android.latestVersionCode)"); process.exit(1); }
const sha = String(json.android?.apkSha256 ?? "").toLowerCase();
console.log(`  newest build ${m.latestVersionCode} (${m.latestVersionName}); builds below ${m.minVersionCode || "none"} are forced to update`);
console.log(`  notes: ${m.notes || "(none)"}`);
console.log(`  link:  ${m.downloadUrl || "(none: the app would never offer an update)"}`);
if (!m.downloadUrl) bad("the download link is missing or not https, so no phone would be offered the update");
if (m.minVersionCode > m.latestVersionCode) bad("minVersionCode is higher than latestVersionCode");
if (!m.apkSizeBytes) console.log("  note  no apkSizeBytes recorded: a truncated download could not be detected");
if (!sha) console.log("  note  no apkSha256 recorded: the file cannot be verified against a checksum");

// ---- 2. what each installed build would see ----------------------------------------------------------------------------
const installed = (opt("installed") ?? Array.from({ length: m.latestVersionCode - 4 }, (_, i) => i + 5).join(","))
  .split(",").map((s) => Number(s.trim())).filter((n) => Number.isInteger(n) && n > 0);
console.log("\nWhat a phone with this build installed would see:");
const WORDS = { none: "nothing (up to date)", optional: "\"An update is available\" (Update now / Later)", required: "\"Update required\" full-screen page" };
for (const code of installed) console.log(`  build ${String(code).padEnd(3)} -> ${WORDS[apkUpdateState(code, m)]}`);

// ---- 3. the download ------------------------------------------------------------------------------------------------------
console.log("\nThe APK:");
const sdk = process.env.ANDROID_HOME || process.env.ANDROID_SDK_ROOT || path.join(process.env.LOCALAPPDATA || os.homedir(), "Android", "Sdk");
const tools = path.join(sdk, "build-tools");
const bt = fs.existsSync(tools) ? fs.readdirSync(tools).sort().at(-1) : undefined;

let file = opt("apk") ? path.resolve(opt("apk")) : undefined;
let temp = false;
if (!file && m.downloadUrl) {
  try {
    const head = await fetch(m.downloadUrl, { headers: { Range: "bytes=0-1023" }, redirect: "follow" });
    const first = new Uint8Array(await head.arrayBuffer()).slice(0, 4);
    const isZip = first[0] === 0x50 && first[1] === 0x4b && first[2] === 3 && first[3] === 4;
    if (head.status === 200 || head.status === 206) ok(`link answers HTTP ${head.status}${isZip ? " and starts like an APK" : ""}`); else bad(`link answers HTTP ${head.status}`);
    if (!isZip) bad("the link does not return an APK (it looks like a web page: a Drive or login page?)");
    const total = Number((head.headers.get("content-range") ?? "").split("/")[1]) || Number(head.headers.get("content-length"));
    if (m.apkSizeBytes && total && head.status === 200 && total === m.apkSizeBytes) ok(`size ${mb(total)} matches the update file`);
    else if (m.apkSizeBytes && total && total !== m.apkSizeBytes && head.status === 206) bad(`the link is ${total} bytes but the update file says ${m.apkSizeBytes}`);
  } catch (e) { bad(`could not reach the link: ${e.message}`); }
  if (!flag("no-download") && problems.length === 0) {
    const res = await fetch(m.downloadUrl, { redirect: "follow" });
    const buf = Buffer.from(await res.arrayBuffer());
    const hex = createHash("sha256").update(buf).digest("hex");
    if (m.apkSizeBytes) (buf.length === m.apkSizeBytes ? ok : bad)(`downloaded ${mb(buf.length)}${buf.length === m.apkSizeBytes ? " = the recorded size" : ` but ${m.apkSizeBytes} bytes were recorded`}`);
    if (sha) (hex === sha ? ok : bad)(hex === sha ? "SHA-256 matches the update file" : `SHA-256 differs from the update file (${hex.slice(0, 12)}... vs ${sha.slice(0, 12)}...)`);
    file = path.join(os.tmpdir(), `veekay-check-${Date.now()}.apk`);
    fs.writeFileSync(file, buf);
    temp = true;
  }
}
if (file && fs.existsSync(file)) {
  if (opt("apk")) {
    const hex = createHash("sha256").update(fs.readFileSync(file)).digest("hex");
    if (sha) (hex === sha ? ok : bad)(hex === sha ? "local APK SHA-256 matches the update file" : "local APK SHA-256 differs from the update file");
  }
  if (bt) {
    const aapt2 = path.join(tools, bt, process.platform === "win32" ? "aapt2.exe" : "aapt2");
    const info = /package: name='([^']+)' versionCode='(\d+)' versionName='([^']*)'/.exec(spawnSync(aapt2, ["dump", "badging", file], { encoding: "utf8" }).stdout || "");
    if (info) {
      (info[1] === "com.veekay.partner" ? ok : bad)(`application id ${info[1]}`);
      (Number(info[2]) === m.latestVersionCode ? ok : bad)(`the APK's own version code is ${info[2]} (the update file says ${m.latestVersionCode})`);
    } else bad("could not read the APK's version with aapt2");
    const signer = path.join(tools, bt, process.platform === "win32" ? "apksigner.bat" : "apksigner");
    const cert = /Signer #1 certificate SHA-256 digest: (\w+)/.exec(spawnSync(signer, ["verify", "--print-certs", file], { encoding: "utf8", shell: process.platform === "win32" }).stdout || "");
    if (cert) ok(`signed with certificate ${cert[1].slice(0, 16)}... (it must be the same on every release, or phones cannot update in place)`);
  } else console.log("  note  Android SDK build-tools not found: the APK's own version and signature were not read");
}
if (temp) fs.rmSync(file, { force: true });

console.log(problems.length ? `\n${problems.length} problem(s) found.\n` : "\nEverything matches: a phone would be offered this update and could download it.\n");
process.exit(problems.length ? 1 : 0);
