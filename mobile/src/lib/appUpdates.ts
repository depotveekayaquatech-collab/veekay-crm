/**
 * In-app updates, two kinds:
 *   OTA  (expo-updates / EAS Update) - JavaScript-only changes. Downloaded in the background, applied only when the
 *        person taps "Restart and update" (or on the next normal launch). Never reloads by itself.
 *   APK  - native / incompatible changes. A small JSON file says which versionCode is newest and which is the minimum;
 *        the app compares it with the installed binary and links to the new APK. Android cannot install silently:
 *        the person opens the download and accepts Android's own install prompt.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { AppState } from "react-native";
import AsyncStorage from "@react-native-async-storage/async-storage";
import * as Application from "expo-application";
import * as Updates from "expo-updates";
import { apkUpdateState, parseManifest, parseVersionCode, type ApkManifest, type ApkUpdateState } from "@/lib/versionPolicy";

/** Where the version file lives. Override per build with EXPO_PUBLIC_UPDATE_MANIFEST_URL. */
const MANIFEST_URL = process.env.EXPO_PUBLIC_UPDATE_MANIFEST_URL || "https://veekay-crm.vercel.app/app-update.json";
const CHECK_EVERY_MS = 30 * 60_000; // never check more often than this, however often the app is opened
const FETCH_TIMEOUT_MS = 10_000;
const DISMISSED_KEY = "veekay.apkUpdateDismissed";

/** Runs `fn` now and each time the app returns to the foreground, at most once per CHECK_EVERY_MS. */
function useThrottledChecks(fn: () => Promise<void>, enabled: boolean) {
  const last = useRef(0);
  const busy = useRef(false);
  const fnRef = useRef(fn);
  fnRef.current = fn;
  useEffect(() => {
    if (!enabled) return;
    const run = async () => {
      if (busy.current || Date.now() - last.current < CHECK_EVERY_MS) return;
      busy.current = true;
      last.current = Date.now(); // a failed attempt also waits: no retry storms while offline
      try {
        await fnRef.current();
      } catch {
        /* offline / service down: the app keeps working */
      } finally {
        busy.current = false;
      }
    };
    void run();
    const sub = AppState.addEventListener("change", (s) => {
      if (s === "active") void run();
    });
    return () => sub.remove();
  }, [enabled]);
}

export function useApkUpdate(enabled: boolean): { state: ApkUpdateState; manifest: ApkManifest | null; dismiss: () => void } {
  const [manifest, setManifest] = useState<ApkManifest | null>(null);
  const [dismissed, setDismissed] = useState<number>(0);
  const installed = parseVersionCode(Application.nativeBuildVersion);

  useEffect(() => {
    AsyncStorage.getItem(DISMISSED_KEY)
      .then((v) => setDismissed(Number(v) || 0))
      .catch(() => undefined);
  }, []);

  useThrottledChecks(async () => {
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), FETCH_TIMEOUT_MS);
    try {
      const res = await fetch(`${MANIFEST_URL}?t=${Date.now()}`, { signal: ctrl.signal, headers: { "Cache-Control": "no-cache" } });
      if (res.ok) setManifest(parseManifest(await res.json()));
    } finally {
      clearTimeout(timer);
    }
  }, enabled && installed > 0);

  const state = apkUpdateState(installed, manifest);
  const dismiss = useCallback(() => {
    if (!manifest) return;
    setDismissed(manifest.latestVersionCode);
    AsyncStorage.setItem(DISMISSED_KEY, String(manifest.latestVersionCode)).catch(() => undefined);
  }, [manifest]);

  // "Later" hides an optional update until a NEWER one is published; a required update can never be dismissed.
  const hidden = state === "optional" && manifest !== null && dismissed >= manifest.latestVersionCode;
  return { state: hidden ? "none" : state, manifest, dismiss };
}

export type OtaPhase = "idle" | "downloading" | "ready";

export function useOtaUpdate(enabled: boolean): { phase: OtaPhase; restart: () => Promise<void>; failed: boolean; progress: number | null } {
  const { isDownloading, isUpdatePending, downloadError, downloadProgress } = Updates.useUpdates();
  const [failed, setFailed] = useState(false);

  // expo-updates is off in development builds / Expo Go; there is nothing to check there.
  useThrottledChecks(async () => {
    setFailed(false);
    const check = await Updates.checkForUpdateAsync();
    if (check.isAvailable) await Updates.fetchUpdateAsync();
  }, enabled && Updates.isEnabled);

  useEffect(() => {
    if (downloadError) setFailed(true);
  }, [downloadError]);

  // Applied only on the person's tap. If the reload itself fails the app simply keeps running the current version.
  const restart = useCallback(async () => {
    try {
      await Updates.reloadAsync();
    } catch {
      setFailed(true);
    }
  }, []);

  const progress = typeof downloadProgress === "number" && downloadProgress > 0 ? Math.min(100, Math.round(downloadProgress * 100)) : null;
  return { phase: isUpdatePending ? "ready" : isDownloading ? "downloading" : "idle", restart, failed, progress };
}
