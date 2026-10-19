import fs from "node:fs";
import type { ExpoConfig } from "expo/config";

/**
 * Veekay Partner (vendor & POC app).
 *
 * BEFORE THE FIRST PLAY STORE UPLOAD decide `ANDROID_PACKAGE`: it is the app's permanent identity on Google Play and
 * can never be changed afterwards. See PLAY_STORE.md.
 */
const ANDROID_PACKAGE = "com.veekay.partner";

// Push messages need Firebase: download google-services.json from the Firebase console into this folder
// (it is not committed). Without it the app still works, just without push.
const googleServices = fs.existsSync("./google-services.json") ? "./google-services.json" : undefined;

// A build that talks plain http (a LAN test build) must also be the development variant, which is what allows cleartext
// traffic on Android. This stops a production build from being made with the https guard switched off by mistake.
if (process.env.EXPO_PUBLIC_ALLOW_HTTP === "1" && process.env.APP_VARIANT !== "development") {
  throw new Error("EXPO_PUBLIC_ALLOW_HTTP=1 is only for LAN test builds (APP_VARIANT=development).");
}

const config: ExpoConfig = {
  name: "Veekay Partner",
  slug: "veekay-partner",
  scheme: "veekaypartner",
  version: "1.2.0",   // 1.2.0: follows the phone's light / dark setting and has a dark splash (native settings), so it needs a new APK. 1.1.0: adds expo-image-manipulator (a native module)
  orientation: "portrait",
  icon: "./assets/icon.png",
  userInterfaceStyle: "automatic",   // lets the app follow the phone's light / dark setting (the in-app Appearance choice can override it)
  backgroundColor: "#FFFFFF",
  android: {
    package: ANDROID_PACKAGE,
    // Lets the in-app updater hand the downloaded APK to Android's installer (Android still asks the person to confirm).
    permissions: ["android.permission.REQUEST_INSTALL_PACKAGES"],
    // Cloud (EAS) builds take the number from EAS (appVersionSource: remote). A LOCAL build uses this one; raise it with
    // ANDROID_VERSION_CODE=5 so a phone accepts it as an update.
    versionCode: Number(process.env.ANDROID_VERSION_CODE) || 1,
    googleServicesFile: googleServices,
    // Tokens live in the Android Keystore; never let an OS backup copy app data to another phone.
    allowBackup: false,
    adaptiveIcon: {
      foregroundImage: "./assets/android-icon-foreground.png",
      backgroundImage: "./assets/android-icon-background.png",
      monochromeImage: "./assets/android-icon-monochrome.png",
    },
    predictiveBackGestureEnabled: true,
    // Only what the app really uses: the camera (to photograph a problem or a document) and notifications.
    // Photos are chosen through the system photo picker, so no storage / media permission is needed.
    blockedPermissions: [
      "android.permission.READ_EXTERNAL_STORAGE",
      "android.permission.WRITE_EXTERNAL_STORAGE",
      "android.permission.READ_MEDIA_IMAGES",
      "android.permission.READ_MEDIA_VIDEO",
      "android.permission.RECORD_AUDIO",
      "android.permission.SYSTEM_ALERT_WINDOW",
      "android.permission.READ_PHONE_STATE",
      "android.permission.RECEIVE_BOOT_COMPLETED",
      "android.permission.ACCESS_BACKGROUND_LOCATION",
    ],
  },
  plugins: [
    "expo-router",
    "expo-secure-store",
    [
      "expo-splash-screen",
      { image: "./assets/splash-icon.png", imageWidth: 200, resizeMode: "contain", backgroundColor: "#FFFFFF", dark: { image: "./assets/splash-icon.png", backgroundColor: "#0A0F1C" } },
    ],
    [
      "expo-image-picker",
      { cameraPermission: "Veekay Partner uses the camera so you can photograph a problem or a document.", microphonePermission: false },
    ],
    ["expo-camera", { cameraPermission: "Veekay uses the camera to read the QR code on a bottle and to photograph bills.", recordAudioAndroid: false }],
    ["expo-location", { locationWhenInUsePermission: "Veekay uses your location only when you check in or out, to record where you were.", isAndroidBackgroundLocationEnabled: false, isAndroidForegroundServiceEnabled: false }],
    ["expo-notifications", { icon: "./assets/android-icon-monochrome.png", color: "#2559C9" }],
    [
      "expo-build-properties",
      {
        android: {
          // Google Play requires new apps and updates to target Android 16 (API 36) from 31 Aug 2026.
          compileSdkVersion: 36,
          targetSdkVersion: 36,
          // Preview and production builds refuse plain http. Only the development build (APP_VARIANT=development,
          // for talking to a server on your own computer) may use it.
          usesCleartextTraffic: process.env.APP_VARIANT === "development",
          // Real phones are ARM. The default also builds x86 / x86_64 (emulators only), which roughly doubles the APK
          // (~22 MB of native libraries per architecture). Keep both ARM ABIs so 32-bit-only phones still install.
          // The development variant (emulator testing) keeps every architecture.
          buildArchs:
            process.env.APP_VARIANT === "development"
              ? ["armeabi-v7a", "arm64-v8a", "x86", "x86_64"]
              : ["armeabi-v7a", "arm64-v8a"],
          enableMinifyInReleaseBuilds: true,
          enableShrinkResourcesInReleaseBuilds: true,
        },
      },
    ],
  ],
  // Over-the-air updates (EAS Update). An update only reaches installs whose runtimeVersion matches. The "appVersion"
  // policy uses `version` above, so changing `version` starts a new update line: bump it for ANY change that needs a new
  // APK (native dependency, permission, app.config plugin / native setting). JS-only changes keep the same `version`.
  runtimeVersion: { policy: "appVersion" },
  updates: {
    url: "https://u.expo.dev/0e2cbd9b-7b3c-4528-8399-a7e61bbc1c17",
    checkAutomatically: "ON_LOAD",
    // EAS cloud builds get their update channel from eas.json. A LOCAL build has none, so it would never receive an
    // over-the-air update; give it the production channel (EAS_BUILD is only set on EAS servers).
    ...(process.env.EAS_BUILD ? {} : { requestHeaders: { "expo-channel-name": "production" } }),
    fallbackToCacheTimeout: 0, // never hold the splash screen waiting for the network; a downloaded update applies on the next start
  },
  experiments: { typedRoutes: true },
  extra: {
  privacyPolicyUrl: process.env.EXPO_PUBLIC_PRIVACY_URL ?? "",
  supportEmail: process.env.EXPO_PUBLIC_SUPPORT_EMAIL ?? "",
  supportPhone: process.env.EXPO_PUBLIC_SUPPORT_PHONE ?? "",
  eas: {
    projectId: "0e2cbd9b-7b3c-4528-8399-a7e61bbc1c17",
  },
},
};

export default config;
