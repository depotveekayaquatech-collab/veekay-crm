# Veekay Partner: releasing the Android app

Direct APK distribution to employees now; Google Play later. Same application ID (`com.veekay.partner`) and same signing key throughout.

## Current build (verified by inspection, 2026-10-17)

| | |
|---|---|
| File | `mobile/build/apk/Veekay-Partner-1.0.1-code9.apk` (git-ignored); the published copy is `public/downloads/` |
| Size / SHA-256 | 56,373,749 bytes / `7f22bcbcad11369cdf5f041c512d4a7266f6e3e4e8206404a7e451e2c1b09132` |
| Application ID, version | `com.veekay.partner`, versionName 1.0.1, versionCode 9 |
| minSdk / targetSdk / compileSdk | 24 (Android 7.0) / 36 (Android 16) / 36 |
| ABIs | arm64-v8a, armeabi-v7a (no x86: emulators on PCs and Chromebooks are not supported by this APK) |
| Signature | APK Signature Scheme v2, one signer `CN=Veekay Aquatech`, RSA 2048, cert SHA-256 `711d9aa84857dcdb54ea4e8d330e145f293da79ad01b7662ed3c3ca01c6b2249` |
| Release flags | not debuggable, `usesCleartextTraffic=false`, `allowBackup=false`, JS bundled in `assets/index.android.bundle` |
| API | `https://veekay-crm-api.fly.dev/api/v1` (checked inside the bundle; no `localhost`/`10.0.2.2`/http reference) |

Verification commands: `aapt2 dump badging`, `apksigner verify --print-certs`, and a zip listing, all from Android SDK build-tools 36.0.0.

## Compatibility

- Runs on Android 7.0+ phones with a 64-bit or 32-bit ARM CPU (nearly every phone sold since 2016).
- Not supported: Android 6 and older, x86 devices/emulators, Wear OS and TV.
- No Google Play installation is required. Push notifications use Firebase Cloud Messaging, so phones **without Google services** (some Huawei models) work but will not receive push alerts.
- Permissions the app asks for, each only when the feature is used: camera (photos, bottle scan), location at check-in/out, notifications (Android 13+). The manifest also carries the badge-count permissions added by `expo-notifications` and `USE_BIOMETRIC`/`USE_FINGERPRINT` from a dependency; remove them before Play if the app does not use them.
- **Offline:** only bottle scans are queued offline and sent later. Everything else needs a connection. Do not tell employees the app "works offline".

## Test matrix (honest status)

No Android device, emulator image or AVD was available when this was built. **No row below has been run.**

| Test | Android 7 (min) | Android 10-12 (mid) | Android 14-16 (recent) |
|---|---|---|---|
| Install + first launch | pending | pending | pending |
| Login / logout | pending | pending | pending |
| Dashboard, stores | pending | pending | pending |
| View orders + authorised update | pending | pending | pending |
| Keyboard, forms, scrolling, back button, gesture and 3-button navigation, cutouts | pending | pending | pending |
| Offline + recovery ([docs/connectivity-device-test.md](../docs/connectivity-device-test.md)) | pending | pending | pending |
| Server error, session expiry | pending | pending | pending |
| Background / resume / process kill | pending | pending | pending |
| Photo upload, document open | pending | pending | pending |
| Install a newer APK over this one (keeps data) | pending | pending | pending |

Minimum before sending to everyone: run the full column on **one real phone** you control (preferably mid-range), and the install-over-the-top row with a code 7 build.

## Installing on an employee phone

1. Send the APK file itself (WhatsApp as a document, email, or a Google Drive file). Check the SHA-256 if you like: Files app > details, or any checksum app.
2. Employee opens the file. Android says the source (e.g. WhatsApp / Chrome / Files) "can't install unknown apps": tap **Settings**, switch on **Allow from this source** for that one app, go back, tap **Install**. This is Android's normal per-app permission; nothing global is turned off. They can switch it off again afterwards.
3. If Play Protect shows "App not scanned" / "Blocked": tap **More details > Install anyway** (the app is signed by Veekay, not by Google Play). Do not ask anyone to disable Play Protect.
4. Open **Veekay Partner**, allow notifications when asked, sign in with the employee ID and password. Location and camera are requested at first use.

## Publishing an update so every phone is alerted (from build 8 on)

Phones with build 6 or newer check `https://veekay-crm.vercel.app/app-update.json` every time the app opens and whenever it returns to the foreground (at most once per 10 minutes). From build 8 the alert's **Update now** button downloads the APK inside the app (progress shown) and opens Android's installer; if that fails it falls back to the browser link. Every profile screen has **Check for updates** and shows `version X (build N)`.

**One command, nothing to upload by hand:** `cd mobile; npm run release -- --notes "What changed"`. It builds the APK, copies it to `public/downloads/` (the web app serves it), writes `public/app-update.json` with its size, SHA-256 and the one-release-behind update policy, and prints the link to check. Then `git add -A`, commit and push: Vercel deploys the file and the alert together. The numbered steps below are the same thing done in pieces (or with a link you host elsewhere, via `--url`).

For each release:
1. Change the code, then (optionally) raise `version` in `app.config.ts` (the visible name, e.g. 1.0.2).
2. `cd mobile; npm run build:apk-local`. The version code is chosen automatically: always above every APK already built and above the one in `public/app-update.json`. The build refuses a code that is not higher.
3. Host `mobile/build/apk/Veekay-Partner-<name>-code<N>.apk` at an https direct-download link (Google Drive: `https://drive.google.com/uc?export=download&id=FILE_ID`; or a public GitHub release).
4. `npm run release:publish -- --url "<that link>" --notes "What changed"`. It reads the real version out of the APK, records its size and SHA-256, refuses a non-upgrading code, and downloads the first bytes of the link to prove it serves an APK and not a web page.
5. Commit and push `public/app-update.json`. When Vercel has deployed, phones show "An update is available" on their next check. This push is what switches the alert on; do it last, after step 4 succeeded.
6. **Update policy (automatic):** step 4 sets the minimum to the *previous* release. A phone one release behind keeps working and is only offered the update; a phone two releases behind gets the full-screen "Update required" page until it updates. Example: publishing 9 after 8 blocks 7 and older; publishing 10 then blocks 8. Pass `--min <code>` to choose differently, `--min 0` to force nobody.

Rules that keep the chain unbroken: same package ID, same signing key, ever-higher version codes. Skip any of these and phones cannot update in place.

Limits: Android always asks the person to confirm the install (nothing is silent), and the first time it asks to allow Veekay Partner to install apps. Builds older than 6 contain no update check at all (build 2 and earlier) or were signed by Expo's key (builds 3 and 4) and cannot update to a locally signed APK.

JavaScript-only fixes can instead go out as an OTA update through EAS Update (channel `production`); that path has not been exercised.

## Build and install a TEST APK (nothing is published, no employee sees it)

```powershell
cd mobile
npm ci                                               # uses mobile\.npmrc (legacy-peer-deps=true): the lean install every local build uses
# Do NOT add --no-legacy-peer-deps to this: it also installs optional libraries the app does not use (reanimated, worklets,
# gesture-handler), which makes the build slower and the APK bigger. The strict flag is only for CHECKING the lockfile:
#   npm ci --include=dev --dry-run --no-legacy-peer-deps      (must end without errors)
npm run typecheck ; npm test                         # type-check and the 28 unit tests
npm run build:apk-local                              # 20-30 minutes the first time; picks the next version code by itself
# the APK appears in mobile\build\apk\Veekay-Partner-<version>-code<N>.apk
```
Install it on a phone (it is signed with the same key as every earlier build, so it installs over the current app and keeps the sign-in; an older EAS-signed build 3 or 4 must be uninstalled first):
```powershell
# Option A: USB cable. On the phone: Settings > About phone > tap "Build number" 7 times > Developer options > USB debugging ON.
& "$env:LOCALAPPDATA\Android\Sdk\platform-tools\adb.exe" devices                      # the phone must be listed (accept the prompt on the phone)
& "$env:LOCALAPPDATA\Android\Sdk\platform-tools\adb.exe" install -r build\apk\Veekay-Partner-1.1.0-code10.apk
# Option B: no cable. Send the .apk file to the phone as a document (WhatsApp, email, Drive), open it, allow "Install unknown apps"
# for that one app when Android asks, then Install. If Play Protect warns: More details > Install anyway.
```
**If the build fails:**
- `OutOfMemoryError: Metaspace` / "Could not receive a message from the daemon": Gradle ran out of memory. The build script already gives it 3 GB of heap and 1 GB of metaspace; on a machine with less RAM set `VEEKAY_GRADLE_JVMARGS` (for example `-Xmx2048m -XX:MaxMetaspaceSize=768m`).
- "There is not enough space on the disk": a build writes about 1.5 GB of working files plus caches, and fails when the drive is full (it did, with 0.3 GB free). Keep at least 4 GB free on the drive that holds the project. If that drive is short, move the build output folders to another drive and leave a junction behind (Gradle sees the same paths; nothing is rebuilt): for each of `android\app\build`, `android\app\.cxx`, and the `android\build` / `android\.cxx` folders of `node_modules\expo-modules-core`, `react-native-screens`, `expo-updates` and `expo`: `robocopy <folder> D:\veekay-build\<name> /MOVE /E` then `New-Item -ItemType Junction -Path <folder> -Target D:\veekay-build\<name>`. Stop the Gradle daemon first (`android\gradlew.bat --stop`).
- A failed build leaves Gradle and Kotlin background processes running (they hold files open). `android\gradlew.bat --stop` ends them.

Check the file before sending: `npm run release:check -- --manifest ../public/app-update.json --apk build/apk/<file>.apk --no-download` (its version, signature and checksum).
To give it to everyone later, follow "Publishing an update" below (`npm run release -- --notes "..."`, then push).

## Checking an update locally (no phone needed)

```
cd mobile
npm run release:check                                   # the LIVE update file: link, size, SHA-256, the APK's own version and signature
npm run release:check -- --manifest ../public/app-update.json --apk build/apk/Veekay-Partner-1.0.1-code9.apk --no-download
                                                        # BEFORE you push: a local update file and a local APK
npm run release:check -- --installed 6,8,9              # what a phone with each build number would see
```
It prints, for each installed build, whether the phone sees nothing, "An update is available" or the full-screen "Update required" page (the same rules the app uses), then downloads the APK and compares size and checksum. Exit code 1 means a problem (a link that returns a web page, a wrong checksum, a version code that differs from the update file).

**On a phone** (the real test): install the previous build, open **Profile > Check for updates**. You should see the newer build offered; **Update now** downloads it inside the app with a progress bar and opens Android's installer; after installing, the app should keep its sign-in (the install-over-the-top step is still untested on a real phone: check it once). To see the **"Update required"** page, publish a test file whose `minVersionCode` is above the installed build (never on the live file while employees are using it).
**Pointing a test build at a different update file:** build with `EXPO_PUBLIC_UPDATE_MANIFEST_URL=https://<your test host>/app-update.json` (compiled into that APK). It must be **https** (the app never opens an http link), so for a file on your own PC use an https tunnel to the web dev server, which serves `public/` (for example `npx localtunnel --port 5173`). Do not use the live URL for experiments.

## The signing key (critical)

- Location: `%USERPROFILE%\.veekay-signing\` (`veekay-release.jks` plus `keystore.properties`). It is outside the repository and is never printed or committed.
- **Back it up now** (password manager or an encrypted USB, in two places). If it is lost, no employee can ever receive an update: they must uninstall (losing any unsent offline scans) and the Play listing cannot be continued with the same identity.
- Earlier EAS cloud APKs (versionCode 3 and 4) were signed with a different, Expo-held key. They are not compatible with this one. Per the earlier handoff none had been installed on employee phones; if any phone has one, it must be uninstalled first, so **first check for unsent scans** (Staff > Scan sync) before removing it.

## Google Play later: checklist

- **APK vs AAB:** the APK is a ready-to-install file for direct sharing. Play requires an **Android App Bundle (.aab)**, from which Google generates optimised APKs per phone. Build it with the same project: `eas build --profile production` (cloud) or `gradlew bundleRelease` in the generated `android/` folder with the same signing config.
- **Signing:** Play uses *Play App Signing*. To keep the same signing identity (so phones with the direct APK can be updated from Play and vice versa), choose the option to **upload your existing app signing key** when creating the app in Play Console (Google documents this with its PEPK tool), then use a separate upload key for future uploads. If you instead let Google generate a new key, Play-installed and directly-installed copies become different lineages and cannot update each other. Decide this before the first upload; it is hard to change.
- **Target API:** the build targets API 36. Checked 2026-10-16 against Google's [target API level requirements](https://support.google.com/googleplay/android-developer/answer/11926878): since 31 Aug 2026, new apps and updates must target Android 16 (API 36) or higher, so this build meets it. Google raises the level every year; re-check at release time.
- **Emulator testing on this PC is blocked** (2026-10-16): the Windows hypervisor is not active (the Android emulator reports no hypervisor driver), about 8 GB of disk is free, and the APK is ARM-only. Enabling "Windows Hypervisor Platform" needs administrator rights and a reboot. Until then, test on a real phone.
- **Policy items to prepare** (none done or submitted): privacy policy URL (the app reads `EXPO_PUBLIC_PRIVACY_URL`), Data safety form (collects name/employee ID, location at check-in, photos, push token), permission declarations, content rating, app-access instructions for reviewers (a test login), store listing text/screenshots, and for new personal developer accounts the closed-testing requirement. Check the current Play Console rules then. `PLAY_STORE.md` has more notes.
- The in-app APK updater needs the `REQUEST_INSTALL_PACKAGES` permission. Google Play restricts that permission and discourages apps that update themselves outside Play. For a Play build, remove it from `app.config.ts` and switch the updater off (let Play deliver updates).
- Nothing has been published, uploaded or created in Play Console.
