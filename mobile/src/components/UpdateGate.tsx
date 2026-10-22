import { useEffect, useState, type ReactNode } from "react";
import { Linking, Text, View } from "react-native";
import * as SplashScreen from "expo-splash-screen";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Button } from "@/components/ui";
import { useAuth } from "@/auth/AuthProvider";
import { useApkUpdate, useOtaUpdate } from "@/lib/appUpdates";
import { downloadAndInstall, InstallError } from "@/lib/apkInstaller";
import { colors, radius, shadow, space } from "@/theme";

/**
 * Wraps the whole app. Normally renders only `children`.
 *  - Installed APK below the minimum version: a full-screen "update required" page (the only blocking case).
 *  - Newer optional APK, or an OTA update downloading / ready: a small banner at the bottom. It never covers a form
 *    or restarts the app by itself, so nobody loses what they are typing.
 */
export function UpdateGate({ children, enabled }: { children: ReactNode; enabled: boolean }) {
  const { account, staff } = useAuth();
  const apk = useApkUpdate(enabled, staff ? "staff" : account ? "partner" : null);     // the update file can treat employees and vendors / POCs differently
  const ota = useOtaUpdate(enabled);
  const insets = useSafeAreaInsets();
  const [otaLater, setOtaLater] = useState(false);
  const [opening, setOpening] = useState(false);
  const [progress, setProgress] = useState<number | null>(null);
  const [problem, setProblem] = useState<string | null>(null);

  /** Downloads the APK in the app and opens Android's installer. If that cannot work, the browser link is the fallback. */
  const download = async () => {
    if (!apk.manifest?.downloadUrl || opening) return;
    setOpening(true);
    setProblem(null);
    setProgress(0);
    try {
      await downloadAndInstall(apk.manifest, setProgress);
    } catch (e) {
      if (e instanceof InstallError) setProblem(e.message);
      else {
        // the in-app route failed (for example the phone's installer or file access): use the browser instead
        try {
          await Linking.openURL(apk.manifest.downloadUrl);
          setProblem("Your browser will download the update. Open the downloaded file to install it.");
        } catch {
          setProblem("Could not download the update. Please check your connection and try again.");
        }
      }
    } finally {
      setOpening(false);
      setProgress(null);
    }
  };
  const label = opening ? (progress !== null && progress > 0 ? `Downloading… ${progress}%` : "Downloading…") : "Update now";
  const blocked = apk.state === "required" && !!apk.manifest;

  // The page below replaces the whole app, so the Navigator (which normally hides the native splash once sign-in has been
  // checked) never runs. Without this the logo stays on top of the "Update required" page and the phone looks frozen.
  useEffect(() => {
    if (blocked) SplashScreen.hideAsync().catch(() => undefined);
  }, [blocked]);

  if (blocked && apk.manifest) {
    return (
      <View style={{ flex: 1, alignItems: "center", justifyContent: "center", padding: space.xxl, gap: space.md, backgroundColor: colors.surface }}>
        <Text style={{ fontSize: 22, fontWeight: "800", color: colors.text, textAlign: "center" }}>Update required</Text>
        <Text style={{ color: colors.textMuted, textAlign: "center", lineHeight: 22 }}>
          A new version of Veekay Partner is required to continue. Tap the button to download and install the latest version ({apk.manifest.latestVersionName}).
        </Text>
        {apk.manifest.notes ? <Text style={{ color: colors.textFaint, textAlign: "center" }}>{apk.manifest.notes}</Text> : null}
        <Button title={opening ? label : "Download and install"} onPress={() => void download()} loading={opening} style={{ alignSelf: "stretch", marginTop: space.sm }} />
        {problem ? <Text style={{ color: colors.danger, textAlign: "center" }}>{problem}</Text> : null}
        <Text style={{ color: colors.textFaint, fontSize: 12, textAlign: "center", lineHeight: 18 }}>
          If Android asks, allow this app to install updates, then tap Install. Your data stays on the phone.
        </Text>
      </View>
    );
  }

  const showApk = apk.state === "optional" && apk.manifest;
  const showOta = !showApk && (ota.phase === "downloading" || (ota.phase === "ready" && !otaLater));

  return (
    <View style={{ flex: 1 }}>
      {children}
      {(showApk || showOta) && (
        <View pointerEvents="box-none" style={{ position: "absolute", left: space.lg, right: space.lg, bottom: Math.max(insets.bottom, space.md) + space.sm }}>
          <View
            accessibilityLiveRegion="polite"
            style={[{ backgroundColor: colors.surface, borderRadius: radius.lg, borderWidth: 1, borderColor: colors.border, padding: space.lg, gap: space.sm }, shadow.card]}
          >
            {showApk && apk.manifest ? (
              <>
                <Text style={{ fontWeight: "800", color: colors.text }}>An update is available</Text>
                <Text style={{ color: colors.textMuted }}>Install version {apk.manifest.latestVersionName} for the latest improvements.</Text>
                <View style={{ flexDirection: "row", gap: space.sm }}>
                  <Button title={label} onPress={() => void download()} loading={opening} style={{ flex: 1 }} />
                  <Button title="Later" variant="secondary" onPress={apk.dismiss} disabled={opening} style={{ flex: 1 }} />
                </View>
                {problem ? <Text style={{ color: colors.danger }}>{problem}</Text> : null}
              </>
            ) : ota.phase === "downloading" ? (
              <>
                <Text style={{ fontWeight: "800", color: colors.text }}>Downloading update…</Text>
                <Text style={{ color: colors.textMuted }}>Please keep the app open.{ota.progress !== null ? ` ${ota.progress}%` : ""}</Text>
              </>
            ) : (
              <>
                <Text style={{ fontWeight: "800", color: colors.text }}>The update is ready</Text>
                <Text style={{ color: colors.textMuted }}>Restart the app to apply it. Anything you have saved stays on the phone.</Text>
                <View style={{ flexDirection: "row", gap: space.sm }}>
                  <Button title="Restart and update" onPress={() => void ota.restart()} style={{ flex: 1 }} />
                  <Button title="Later" variant="secondary" onPress={() => setOtaLater(true)} style={{ flex: 1 }} />
                </View>
              </>
            )}
          </View>
        </View>
      )}
    </View>
  );
}
