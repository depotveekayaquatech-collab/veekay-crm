/**
 * Writes public/app-update.json for a finished APK, so every phone with the app shows "An update is available".
 *
 *   npm run release:publish -- --url "https://.../Veekay-Partner-1.0.1-code8.apk" --notes "What changed"
 *   options: --apk <file>   (default: the highest-code APK in mobile/build/apk)
 *            --min <code>   (force everyone below this code to update; default 0 = nobody is forced)
 *            --force        (allow a version code that is not higher than the published one: never for real releases)
 *            --skip-verify  (do not test the link)
 *
 * It reads the real version out of the APK, records its size and SHA-256, refuses a code that phones would not accept
 * as an update, and downloads the first bytes of the link to prove it serves an APK (not a Drive/login web page).
 * It only edits the file. Commit and push it afterwards; that deployment is what switches the alert on.
 */
import { createHash } from "node:crypto";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { buildManifest, codeFromFileName, looksLikeApk } from "./release-lib.mjs";

const mobile = path.resolve(import.meta.dirname, "..");
const apkDir = path.join(mobile, "build", "apk");
const manifestFile = path.resolve(mobile, "..", "public", "app-update.json");
const die = (m) => { console.error(`\nERROR: ${m}\n`); process.exit(1); };

const args = process.argv.slice(2);
const opt = (n) => { const i = args.indexOf(`--${n}`); return i >= 0 ? args[i + 1] : undefined; };
const flag = (n) => args.includes(`--${n}`);

const url = opt("url");
if (!url) die('Missing --url "https://...". Host the APK first, then pass its direct-download link.');

let apk = opt("apk");
if (!apk) {
  const all = fs.existsSync(apkDir) ? fs.readdirSync(apkDir).filter((f) => f.endsWith(".apk")).sort((a, b) => codeFromFileName(b) - codeFromFileName(a)) : [];
  if (!all.length) die(`No APK in ${apkDir}. Build one first: npm run build:apk-local`);
  apk = path.join(apkDir, all[0]);
}
if (!fs.existsSync(apk)) die(`APK not found: ${apk}`);

// the real identity of the APK, from the Android SDK's aapt2
const sdk = process.env.ANDROID_HOME || process.env.ANDROID_SDK_ROOT || path.join(process.env.LOCALAPPDATA || os.homedir(), "Android", "Sdk");
const btRoot = path.join(sdk, "build-tools");
const bt = fs.existsSync(btRoot) ? fs.readdirSync(btRoot).sort().at(-1) : undefined;
if (!bt) die(`Android build-tools not found under ${sdk}.`);
const aapt2 = path.join(btRoot, bt, process.platform === "win32" ? "aapt2.exe" : "aapt2");
const out = spawnSync(aapt2, ["dump", "badging", apk], { encoding: "utf8" });
const m = /package: name='([^']+)' versionCode='(\d+)' versionName='([^']*)'/.exec(out.stdout || "");
if (!m) die("Could not read the APK's version with aapt2.");
const [, pkg, codeText, name] = m;
if (pkg !== "com.veekay.partner") die(`Unexpected application id ${pkg}.`);
const code = Number(codeText);

const bytes = fs.readFileSync(apk);
const sha256 = createHash("sha256").update(bytes).digest("hex");

let previousLatest = 0;
try { previousLatest = Number(JSON.parse(fs.readFileSync(manifestFile, "utf8")).android?.latestVersionCode) || 0; } catch { /* first release */ }

let manifest;
try {
  manifest = buildManifest({ code, name, url, notes: opt("notes") ?? "", minCode: Number(opt("min") ?? 0), sizeBytes: bytes.length, sha256, previousLatest, force: flag("force") });
} catch (e) { die(e.message); }

if (!flag("skip-verify")) {
  const ctl = new AbortController();
  const timer = setTimeout(() => ctl.abort(), 30_000);
  try {
    const res = await fetch(url, { headers: { Range: "bytes=0-1023" }, signal: ctl.signal, redirect: "follow" });
    if (!res.ok) die(`The link answered HTTP ${res.status}. Open it in a browser and fix the sharing settings.`);
    const first = new Uint8Array((await res.body.getReader().read()).value ?? []);
    ctl.abort();
    if (!looksLikeApk(first)) die("The link does not return an APK file (it looks like a web page). Use a direct-download link.");
    const type = res.headers.get("content-type") ?? "";
    console.log(`Link check: HTTP ${res.status}, starts like an APK (${type || "no content-type"}).`);
  } catch (e) {
    if (e?.name !== "AbortError") die(`Could not reach the link: ${e.message}`);
  } finally { clearTimeout(timer); }
}

fs.writeFileSync(manifestFile, JSON.stringify(manifest, null, 2) + "\n");
console.log(`\nPublished in ${path.relative(process.cwd(), manifestFile)}:`);
console.log(`  ${path.basename(apk)}  versionCode ${code}  versionName ${name}  ${(bytes.length / 1048576).toFixed(1)} MB`);
console.log(`  sha256 ${sha256}`);
console.log(`  forced for builds below ${manifest.android.minVersionCode || "nobody"}`);
console.log("\nNext: commit and push public/app-update.json. When the web app has deployed, phones show the update on their next check.");
