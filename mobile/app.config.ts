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
  version: "1.0.0",
  orientation: "portrait",
  icon: "./assets/icon.png",
  userInterfaceStyle: "light",
  backgroundColor: "#FFFFFF",
  android: {
    package: ANDROID_PACKAGE,
    versionCode: 1,
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
      { image: "./assets/splash-icon.png", imageWidth: 200, resizeMode: "contain", backgroundColor: "#FFFFFF" },
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
          enableMinifyInReleaseBuilds: true,
          enableShrinkResourcesInReleaseBuilds: true,
        },
      },
    ],
  ],
  experiments: { typedRoutes: true },
  extra: {
    privacyPolicyUrl: process.env.EXPO_PUBLIC_PRIVACY_URL ?? "",
    supportEmail: process.env.EXPO_PUBLIC_SUPPORT_EMAIL ?? "",
    supportPhone: process.env.EXPO_PUBLIC_SUPPORT_PHONE ?? "",
  },
};

export default config;
