# Veekay Partner (vendor and POC app)

A native Android app built with React Native (Expo SDK 57, Expo Router). It talks to the Veekay API under
`/api/v1/external/*`; the same API the web version at `/vendor` uses.

- **Store POC:** raises tickets (with photos), replies, confirms or flags deliveries, uploads cards and payment proofs.
- **Veekay employee:** signs in with an Employee ID. Check in / out with location, leave, marking orders for several dates at once, offline-safe bottle scanning, cash purchases with a bill photo.
- **Vendor:** follows orders, tickets, deliveries, bills and bottles of their stores. Read-only, enforced by the server.

## Run it on a phone while developing

```bash
cd mobile
npm install --legacy-peer-deps      # this folder sits next to the web app; keep its dependencies separate
cp .env.example .env                # set EXPO_PUBLIC_API_URL
npx expo start                      # then open in a development build (see below)
```

The app uses native modules (secure storage, notifications), so use a **development build**, not Expo Go:

```bash
npx eas-cli login
npx eas-cli build --platform android --profile development     # installs as an APK on your phone
```

Development builds may use `http://<your-computer-LAN-IP>:8000/api/v1`. Preview and production builds refuse anything that
is not `https`, and the app shows a setup error instead of starting with a wrong address.

Checks: `npm run typecheck`, `npx expo-doctor`, and `npx expo export --platform android` (a full release bundle).

## Launching for testers

See [docs/MOBILE_LAUNCH.md](../docs/MOBILE_LAUNCH.md): server and database order, the 10:00 sync trigger, passwords, building, the beta plan and day-to-day running.

## Releasing

See **[PLAY_STORE.md](PLAY_STORE.md)** for the full Google Play checklist. In short:

```bash
npx eas-cli env:create --name EXPO_PUBLIC_API_URL --value https://YOUR-API/api/v1 --environment production --visibility plaintext
npx eas-cli env:create --name EXPO_PUBLIC_PRIVACY_URL ... (and EXPO_PUBLIC_SUPPORT_EMAIL, EXPO_PUBLIC_SUPPORT_PHONE)
npm run build:aab                    # signed Android App Bundle (.aab) for the Play Console
npx eas-cli submit --platform android --profile production    # or upload the .aab by hand
```

## Push notifications

Optional until you set up Firebase: create a Firebase project, add an Android app with the package name from
`app.config.ts`, download `google-services.json` into this folder (it is git-ignored), and upload an FCM service-account
key to EAS (`eas credentials`). On the server set `FIREBASE_CREDENTIALS_FILE` and `pip install firebase-admin`.
Without this the app works fully; alerts then appear in the Alerts tab.

## Layout

```
src/app/        screens (Expo Router: every file is a route)
src/api/        API client (tokens, refresh, timeouts), types, data hooks
src/components/ shared UI
src/lib/        formatting, push, photo / file helpers
store/          Play Store assets and text (icon, listing, privacy policy draft)
```

Tokens: the access token lives in memory; the refresh token is in the Android Keystore (`expo-secure-store`) and rotates on
every use. Android backups are disabled so tokens never travel to another phone.

> `metro.config.js` makes the app ignore the web app's `node_modules` in the parent folder. For a long-lived Play Store app
> it is cleaner to move `mobile/` into its own repository.
