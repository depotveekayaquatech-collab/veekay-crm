# Updates for Veekay Partner (private APK distribution)

Two kinds of update, and which to use:

| Change | How it reaches phones |
|---|---|
| JavaScript / UI only (text, screens, logic, bug fix) | **OTA** with EAS Update. No new APK. |
| Anything native: new/changed native package, permission, `app.config.ts` plugin or native setting, Expo SDK upgrade | **New APK**. Employees install it. |

## How it works in the app
- **OTA** (`expo-updates`): checks when the app starts and each time it returns to the foreground (at most every 30 min).
  It downloads quietly, shows "Downloading update… NN%", then "The update is ready" with **Restart and update** / **Later**.
  It never restarts by itself, so nobody loses a form. An update downloaded but not applied is applied on the next normal start.
  Offline or service down: the check just fails silently and the app keeps running.
- **APK**: the app reads `https://veekay-crm.vercel.app/app-update.json` (the file `public/app-update.json` in the CRM repo,
  published by Vercel on push). Installed `versionCode` below `latestVersionCode` shows "An update is available" with
  **Update now** / **Later** ("Later" hides it until a newer one is published). Installed below `minVersionCode` shows a full-screen
  **Update required** page with **Download update**. Android cannot install an APK silently: the person opens the downloaded file
  and accepts Android's own prompt ("allow installing from this source" the first time). A manifest with an empty or non-https
  `downloadUrl` never blocks anyone.
- The installed `versionCode` is read from the binary (`expo-application`), numbers are compared as numbers.

## Versions: what to bump
- `version` in `app.config.ts` ("1.0.0") is also the **OTA runtime version** (`runtimeVersion.policy = "appVersion"`).
  An OTA only reaches installs built with the same `version`. **Whenever a change needs a new APK, also bump `version`**
  (e.g. 1.0.0 -> 1.1.0) so old APKs never receive JavaScript that needs the new native code.
- `versionCode` (Android build number) is managed by EAS (`appVersionSource: remote`); the `preview` and `production` profiles
  auto-increment it per build. See the current value: `npx eas-cli build:version:get -p android`. Set one explicitly:
  `npx eas-cli build:version:set -p android`. After a build, use that build's number as `latestVersionCode` in the manifest.

## One-time setup (PowerShell, from `mobile/`)
```powershell
npm ci                                   # strict install; must finish without peer-dependency errors
npx eas-cli login
npx eas-cli whoami
# API address for cloud builds (the local .env is NOT uploaded; without this the APK opens on "App setup incomplete").
# The PREVIEW environment already has it (set during the first preview build). Production does not yet:
npx eas-cli env:create preview --name EXPO_PUBLIC_API_URL --value https://veekay-crm-api.fly.dev/api/v1 --visibility plaintext --scope project --non-interactive   # (env:create works but prints a deprecation notice; env:set is the newer name)
npx eas-cli env:create production --name EXPO_PUBLIC_API_URL --value https://veekay-crm-api.fly.dev/api/v1 --visibility plaintext --scope project --non-interactive
npx eas-cli env:list --environment preview
# (repeat env:create for these only if you use them: EXPO_PUBLIC_PRIVACY_URL, EXPO_PUBLIC_SUPPORT_EMAIL, EXPO_PUBLIC_SUPPORT_PHONE)
```
Push notifications need `google-services.json`: add it in EAS as a file variable (`eas env:create ... --type file`) and point
`googleServicesFile` at it; it is deliberately not uploaded from disk.

## Build a new APK (preview = installable APK, channel "preview")
```powershell
cd mobile
# 1. if native things changed: bump "version" in app.config.ts
npm run typecheck
npx expo-doctor
npx eas-cli build --platform android --profile preview
```
The build page gives an APK link. Test on one phone first (checklist below).

## Make a new APK available to employees
1. Host the APK at a stable https link, e.g. a **GitHub Release** asset of this repo (free, stable):
   `gh release create partner-v1.1.0 .\Veekay-Partner-1.1.0.apk --title "Veekay Partner 1.1.0"` -> use the asset URL.
   (The EAS build page link also works but expires; do not use it as the permanent link.)
2. Edit `public/app-update.json` in the CRM repo:
```json
{ "android": { "latestVersionCode": 2, "latestVersionName": "1.1.0", "minVersionCode": 0,
  "downloadUrl": "https://github.com/<owner>/<repo>/releases/download/partner-v1.1.0/Veekay-Partner-1.1.0.apk",
  "notes": "What changed." } }
```
   `minVersionCode` stays low for an **optional** update; raise it to `latestVersionCode` only when old versions must stop working
   (**mandatory**). Do that only after employees have had time to install.
3. Commit and push; Vercel serves the new file within about a minute. Check: open `https://veekay-crm.vercel.app/app-update.json`.

## Publish an OTA update (JavaScript-only change)
```powershell
cd mobile
npm run typecheck
npx expo start                           # test the change locally first
# Publish to the TEST channel first (a phone built with the preview profile):
npx eas-cli update --channel preview --message "Fix: <what>"
# Only after it works on a test phone, and with your approval, to employees on production-profile builds:
npx eas-cli update --channel production --message "Fix: <what>"
```
Verify: on a phone with the matching build, close and reopen the app (or bring it to the foreground); the banner appears
and "Restart and update" applies it. `npx eas-cli update:list --branch preview` shows what is published;
`npx eas-cli update:rollback` / republishing an earlier update undoes a bad one.
Channels: `preview` profile builds listen on channel "preview", `production` builds on "production".
Note: employees on private APKs from the `preview` profile get OTAs published to channel **preview**.

## Test the APK-update alert without touching employees
Build an APK, then point a test copy at a test manifest: host a JSON like the one above anywhere on https with
`latestVersionCode` higher than the installed one, build with `EXPO_PUBLIC_UPDATE_MANIFEST_URL=<that url>` set for the build,
install, open the app. For the mandatory page set `minVersionCode` above the installed code.

## Checklist: test on one phone before sending to employees
1. Install the APK (allow "install unknown apps" for the file manager/browser used). App opens, no "setup incomplete" screen.
2. Sign in with a **test** employee account; name and role are correct; wrong password shows an error; sign out and in again.
3. Home/orders/stores show only that employee's data. Pull to refresh works.
4. Airplane mode: screens show a clear offline message; nothing claims data was saved; scans queue and say they are pending.
5. Back online: queued scans send; refresh keeps saved data.
6. Leave the app 30+ minutes, reopen: no crash; session still valid (or a clean sign-in prompt).
7. Update alert (see above) and OTA banner behave as described.
8. Compare what you saved on the phone with the web CRM.

## Separate updates for employees and for vendors / POCs

One app serves both, so the update file can give each its own rules (needs build 20 or later installed first):

```json
{ "android": { "latestVersionCode": 20, "minVersionCode": 18, "downloadUrl": "...",       // shared rules (signed out, old builds)
               "staff":   { "latestVersionCode": 22, ... },                                  // Veekay employees only
               "partner": { "latestVersionCode": 21, ... } } }                               // vendors / POCs only
```

A signed-in person follows the shared rules with their own section laid over them; a section with a `latestVersionCode` is a whole release
(build, link, size, notes, minimum). Publish with `--audience`:

```
npm run release:publish -- --audience both    --notes "..."   # everyone (default); clears the separate sections
npm run release:publish -- --audience staff   --notes "..."   # only employees are offered it; vendors / POCs stay put
npm run release:publish -- --audience partner --notes "..."   # only vendors / POCs
```

- The first release made with an app that understands this must be `both`; separate sections only work after that.
- A release keeps the minimum that already applies to its audience (nobody is newly forced); pass `--min <build>` to force one.
- APK files the file still points at stay in `public/downloads/`; older ones are removed.
- `npm run release:check -- --audience staff` shows what an employee would see.
