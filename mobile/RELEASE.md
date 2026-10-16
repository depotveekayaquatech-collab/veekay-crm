# Veekay Partner: releasing the Android app

Direct APK distribution to employees now; Google Play later. Same application ID (`com.veekay.partner`) and same signing key throughout.

## Current build (verified by inspection, 2026-10-16)

| | |
|---|---|
| File | `mobile/build/apk/Veekay-Partner-1.0.0-code6.apk` (git-ignored) |
| Size / SHA-256 | 56,318,257 bytes / `703a1dc8c8ca53aeaef1ed9ba57e20528b9ab8a9bb2c954c921b8bf754709131` |
| Application ID, version | `com.veekay.partner`, versionName 1.0.0, versionCode 6 |
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

## Updating (no data loss)

1. Edit code, then raise the number: `$env:ANDROID_VERSION_CODE=7` (always higher than any APK already shared; never reuse a number). Bump `version` in `app.config.ts` for a visible name (e.g. 1.0.1).
2. From `mobile/`: `npm run build:apk-local`. It uses the same key and package, so Android treats it as an **update**: employees open the new APK and tap **Update**; login and queued scans are kept.
3. Never ship a debug build, never change the package ID, never build with a different key.
4. JavaScript-only fixes can instead go out as an OTA update through EAS Update (channel `production`) without a new APK; the build embeds that channel. Native changes always need a new APK.

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
- Nothing has been published, uploaded or created in Play Console.
