/**
 * Local standalone release APK (no EAS, no cloud, no expiring links).
 *
 *   cd mobile
 *   npm run build:apk-local                 # versionCode from ANDROID_VERSION_CODE (default: next number, see below)
 *   $env:ANDROID_VERSION_CODE=6; npm run build:apk-local
 *
 * What it does: regenerates the git-ignored android/ project from app.config.ts, points Gradle at the Android SDK,
 * signs the release with YOUR private key (%USERPROFILE%\.veekay-signing, created once, never committed) and builds
 * `assembleRelease`. The APK is copied to mobile/build/apk/. The web CRM, the backend and production data are untouched.
 *
 * Needs: JDK 17+ on PATH, the Android SDK (platform 36, build-tools 36, NDK 27) and the signing key. BACK UP the
 * signing folder: with a different key a phone refuses the APK as an update and the app must be uninstalled first.
 */
import { spawnSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { codeFromFileName, nextVersionCode } from "./release-lib.mjs";

const mobile = path.resolve(import.meta.dirname, "..");
const android = path.join(mobile, "android");
const win = process.platform === "win32";

const die = (m) => {
  console.error(`\nERROR: ${m}\n`);
  process.exit(1);
};
const run = (cmd, args, opts = {}) => {
  console.log(`\n> ${cmd} ${args.join(" ")}`);
  const r = spawnSync(cmd, args, { stdio: "inherit", shell: win, cwd: mobile, ...opts });
  if (r.status !== 0) die(`${cmd} failed (exit ${r.status}).`);
};

// ---- 1. signing key (private, outside the repository)
const keyDir = process.env.VEEKAY_SIGNING_DIR || path.join(os.homedir(), ".veekay-signing");
const propsFile = path.join(keyDir, "keystore.properties");
if (!fs.existsSync(propsFile)) die(`No signing key found in ${keyDir}. Create it once (see mobile/UPDATES.md, "Local build").`);
const props = Object.fromEntries(
  fs.readFileSync(propsFile, "utf8").split(/\r?\n/).filter((l) => l.includes("=")).map((l) => [l.slice(0, l.indexOf("=")), l.slice(l.indexOf("=") + 1)]),
);
for (const k of ["storeFile", "storePassword", "keyAlias", "keyPassword"]) if (!props[k]) die(`keystore.properties is missing ${k}.`);
if (!fs.existsSync(props.storeFile)) die(`Keystore file not found: ${props.storeFile}`);

// ---- 2. Android SDK
const sdk = process.env.ANDROID_HOME || process.env.ANDROID_SDK_ROOT || path.join(process.env.LOCALAPPDATA || "", "Android", "Sdk");
if (!fs.existsSync(path.join(sdk, "platforms"))) die(`Android SDK not found (looked in ${sdk}). Set ANDROID_HOME.`);

// ---- 2b. the production API address that gets baked into the APK (Expo reads the shell first, then mobile/.env)
const apiUrl = (process.env.EXPO_PUBLIC_API_URL ||
  (fs.existsSync(path.join(mobile, ".env")) ? (fs.readFileSync(path.join(mobile, ".env"), "utf8").match(/^EXPO_PUBLIC_API_URL=(.+)$/m)?.[1] ?? "") : "")).trim().replace(/\/+$/, "");
if (!/^https:\/\/.+\/api\/v1$/.test(apiUrl)) die(`EXPO_PUBLIC_API_URL must be an https address ending in /api/v1 (got "${apiUrl || "nothing"}"). Fix mobile/.env.`);
console.log(`API address in this build: ${apiUrl}`);

// ---- 3. version code (a phone only accepts an APK as an update if this number is higher than the installed one)
const apkOut = path.join(mobile, "build", "apk");
const builtCodes = fs.existsSync(apkOut) ? fs.readdirSync(apkOut).map((f) => codeFromFileName(f)).filter(Boolean) : [];
let published = 0;
try { published = Number(JSON.parse(fs.readFileSync(path.resolve(mobile, "..", "public", "app-update.json"), "utf8")).android?.latestVersionCode) || 0; } catch { /* none yet */ }
const highest = Math.max(0, published, ...builtCodes);
const versionCode = process.env.ANDROID_VERSION_CODE || String(nextVersionCode(builtCodes, published));
// A phone only accepts an APK as an update when its code is HIGHER than the installed one. Never rebuild a number that
// was already built or announced (set VEEKAY_ALLOW_REUSE_CODE=1 only for a throw-away test build).
if (Number(versionCode) <= highest && !process.env.VEEKAY_ALLOW_REUSE_CODE) {
  die(`Version code ${versionCode} is not higher than ${highest} (already built or published). Use ANDROID_VERSION_CODE=${highest + 1} or leave it unset.`);
}
console.log(`Building version ${versionCode}, signed with ${path.basename(props.storeFile)} (alias ${props.keyAlias}), SDK ${sdk}`);

// ---- 4. regenerate the native project from app.config.ts (android/ is generated and git-ignored)
const env = { ...process.env, ANDROID_VERSION_CODE: versionCode, NODE_ENV: "production", ANDROID_HOME: sdk };

// Android's native build step fails under JDK 24+ ("A restricted method in java.lang.System has been called"), and this
// toolchain targets JDK 17. Use a portable JDK 17 when one is available (~\.veekay-jdk17, or VEEKAY_JDK17).
const jdkRoot = process.env.VEEKAY_JDK17 || path.join(os.homedir(), ".veekay-jdk17");
const jdk17 = fs.existsSync(jdkRoot) ? fs.readdirSync(jdkRoot).find((d) => /^jdk-17/.test(d)) : undefined;
if (jdk17) {
  env.JAVA_HOME = path.join(jdkRoot, jdk17);
  // Windows names the variable `Path`; writing `PATH` next to it would shadow the real one with "...;undefined".
  const pathKey = Object.keys(env).find((k) => k.toLowerCase() === "path") ?? "PATH";
  env[pathKey] = `${path.join(env.JAVA_HOME, "bin")}${path.delimiter}${env[pathKey] ?? ""}`;
  console.log(`Using JDK 17: ${env.JAVA_HOME}`);
} else {
  console.warn("WARNING: no JDK 17 found; on JDK 24+ the native build step is expected to fail (see mobile/UPDATES.md).");
}
run("npx", ["expo", "prebuild", "--platform", "android", "--no-install"], { env });
fs.writeFileSync(path.join(android, "local.properties"), `sdk.dir=${sdk.replace(/\\/g, "\\\\").replace(":", "\\:")}\n`);

// ---- 5. sign the release build with the private key (credentials come from the environment, never written to disk)
const gradleFile = path.join(android, "app", "build.gradle");
let g = fs.readFileSync(gradleFile, "utf8");
if (!g.includes("VEEKAY_KEYSTORE")) {
  const releaseCfg = `
        release {
            storeFile file(System.getenv("VEEKAY_KEYSTORE"))
            storePassword System.getenv("VEEKAY_KEYSTORE_PASSWORD")
            keyAlias System.getenv("VEEKAY_KEY_ALIAS")
            keyPassword System.getenv("VEEKAY_KEY_PASSWORD")
        }`;
  g = g.replace(/(signingConfigs\s*\{\s*debug\s*\{[^}]*\})/, `$1${releaseCfg}`);
  const i = g.indexOf("release {", g.indexOf("buildTypes"));
  if (i < 0) die("Could not find the release build type in android/app/build.gradle.");
  const j = g.indexOf("signingConfig signingConfigs.debug", i);
  if (j < 0) die("Could not find the release signingConfig line to replace.");
  g = g.slice(0, j) + "signingConfig signingConfigs.release" + g.slice(j + "signingConfig signingConfigs.debug".length);
  fs.writeFileSync(gradleFile, g);
}
env.VEEKAY_KEYSTORE = props.storeFile;
env.VEEKAY_KEYSTORE_PASSWORD = props.storePassword;
env.VEEKAY_KEY_ALIAS = props.keyAlias;
env.VEEKAY_KEY_PASSWORD = props.keyPassword;

// ---- 6. build
run(win ? ".\\gradlew.bat" : "./gradlew", ["assembleRelease", "--console=plain"], { cwd: android, env });

// JDK 25 only builds the native parts reliably with a normal Gradle daemon (the single-use `--no-daemon` mode fails); stop it when done
spawnSync(win ? ".\\gradlew.bat" : "./gradlew", ["--stop"], { cwd: android, shell: win, stdio: "ignore", env });

const apk = path.join(android, "app", "build", "outputs", "apk", "release", "app-release.apk");
if (!fs.existsSync(apk)) die("Gradle finished but app-release.apk was not produced.");
const out = path.join(mobile, "build", "apk");
fs.mkdirSync(out, { recursive: true });
const versionName = /^\s{2}version:\s*"([^"]+)"/m.exec(fs.readFileSync(path.join(mobile, "app.config.ts"), "utf8"))?.[1] ?? "1.0.0";
const dest = path.join(out, `Veekay-Partner-${versionName}-code${versionCode}.apk`);
fs.copyFileSync(apk, dest);
console.log(`\nDONE: ${dest}\nSize: ${(fs.statSync(dest).size / 1e6).toFixed(1)} MB`);
