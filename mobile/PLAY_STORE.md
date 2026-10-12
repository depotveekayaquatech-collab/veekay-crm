# Google Play release checklist

What the code already does, and what only you can do in the Play Console.

## Already handled in the app

| Play requirement | How the app meets it |
|---|---|
| **Target Android 16 (API 36)** — required for new apps and updates from 31 Aug 2026 | `targetSdkVersion` / `compileSdkVersion` pinned to 36 in `app.config.ts` |
| **Android App Bundle (.aab)**, not APK | `eas.json` production profile builds `app-bundle` |
| **Play App Signing** | EAS creates the upload key; Google holds the app-signing key once you enrol |
| **64-bit, current toolchain** | Expo SDK 57 / React Native 0.86 default |
| **Minimal permissions** | Merged manifest asks only for INTERNET, CAMERA (bottle QR scanning, photos of bills and problems), foreground LOCATION (attendance check-in / out), POST_NOTIFICATIONS, VIBRATE. Background location, storage, media, audio, phone-state and boot permissions are removed. Photos come from the system photo picker |
| **Secure traffic** | `usesCleartextTraffic` is off in preview and production; the app refuses to start with a non-https server address |
| **Sensitive data at rest** | Refresh token in the Android Keystore; Android backup disabled |
| **Runtime permissions with a reason** | Camera and notifications are requested only when used, with an explanation; the app works if they are denied |
| **Accessibility** | Roles, labels and states on controls, 48dp touch targets, supports system font scaling |
| **Login-gated app** | Test credentials go in *App access* (below) |
| **Account deletion** | Accounts are created by Veekay, not in the app, so Play's in-app account-creation deletion rule does not apply. The app still has *Request data deletion* and the privacy policy covers it |

## You must decide before the first upload

1. **Application ID.** `ANDROID_PACKAGE` in `app.config.ts` (now `com.veekay.partner`). It is permanent once published.
2. **App name and icon.** Name is "Veekay Partner"; a 512×512 icon is in `store/play-icon-512.png`.
3. **Production API URL** (https) and **support phone / email** — set as EAS environment variables (see README).
4. **Privacy policy URL** — publish `store/PRIVACY_POLICY.md` (after a legal read) on a public https page and use that URL in the Play Console and `EXPO_PUBLIC_PRIVACY_URL`.

## Play Console steps

1. **Developer account.** An *organisation* account is exempt from the closed-testing rule below. A *personal* account created after 13 Nov 2023 must first run a **closed test with at least 12 testers opted in for 14 continuous days** before *Production* unlocks ([Google's rule](https://support.google.com/googleplay/android-developer/answer/14151465)). If you can, register as an organisation.
2. **Create the app** → Free, App (not game). Declare it is **not** for children (target audience 18+).
3. **Store listing** — text in `store/listing.md`. Needs: 512×512 icon, a 1024×500 feature graphic, and at least 2 phone screenshots (take them on a real phone from the preview build).
4. **App access** — choose *All or some functionality is restricted* and give Google a working **POC** login and a **vendor** login (plus the exact steps). Use real accounts on a staging server, never production customers.
5. **Data safety form** — answers below.
6. **Content rating** questionnaire — a business tool: no violence, no user-generated public content, no location, no purchases. Expect "Everyone".
7. **Ads** — no ads. **Government / news / health / finance** declarations — none apply.
8. **Upload** the `.aab` to *Internal testing* first, test on real devices, then *Closed testing*, then *Production* with a staged rollout (for example 20% then 100%).

## Data safety form answers

Data is **encrypted in transit** (https). Users can **request deletion** (in-app *Request data deletion* and by email). Nothing is sold; nothing is shared with third parties for ads. Firebase Cloud Messaging is used only to deliver notifications.

| Data | Collected | Purpose | Optional? |
|---|---|---|---|
| Name | Yes | App functionality, account management | No |
| Email address | Yes | Account management (it is the login) | No |
| Phone number | Yes | App functionality (contact for the store) | No |
| Photos | Yes, only when the user attaches one | App functionality (ticket and delivery evidence) | Yes |
| Files and docs (PDFs / photos of documents) | Yes, only when uploaded | App functionality (compliance documents) | Yes |
| Other user-generated content (ticket text) | Yes | App functionality | No |
| App activity / in-app actions | Yes (audit log of tickets, uploads) | App functionality, security | No |
| Device or other IDs (push token) | Yes, if notifications allowed | App functionality (notifications) | Yes |
| Approximate and precise location (employees only) | Yes, once at each attendance check-in / out, only while the app is open | App functionality (attendance) | Yes (check-in works without it) |
| Financial info: purchase amounts entered by employees (cash purchases) | Yes | App functionality | No |
| Contacts, health, background location | **No** | | |

## Employee features (same app)

Veekay employees sign in with their Employee ID in the same app. In the *Data safety* form tick **Location** (collected, not shared, for app functionality, optional) in addition to the table above. In the **Permissions declaration** there is nothing special to submit: only *foreground* location is used. Give Google a test **employee** login as well as a POC and a vendor login in *App access*, and say which tab each permission unlocks (Scan needs the camera, Today needs location).

## Before every release

- Bump nothing by hand: `autoIncrement` raises `versionCode` on each production build; change `version` in `app.config.ts` for user-visible versions.
- `npm run typecheck`, `npx expo-doctor`, `npx expo export --platform android`, then test the `preview` APK on a real phone: sign in as a POC and as a vendor, raise a ticket with a photo, upload a document, open it, confirm a delivery, sign out.
- Check the **Pre-launch report** and **Android vitals** in the Play Console after each upload.
