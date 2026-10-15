import { useState, type ReactNode } from "react";
import { Linking, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Button } from "@/components/ui";
import { useApkUpdate, useOtaUpdate } from "@/lib/appUpdates";
import { colors, radius, shadow, space } from "@/theme";

/**
 * Wraps the whole app. Normally renders only `children`.
 *  - Installed APK below the minimum version: a full-screen "update required" page (the only blocking case).
 *  - Newer optional APK, or an OTA update downloading / ready: a small banner at the bottom. It never covers a form
 *    or restarts the app by itself, so nobody loses what they are typing.
 */
export function UpdateGate({ children, enabled }: { children: ReactNode; enabled: boolean }) {
  const apk = useApkUpdate(enabled);
  const ota = useOtaUpdate(enabled);
  const insets = useSafeAreaInsets();
  const [otaLater, setOtaLater] = useState(false);
  const [opening, setOpening] = useState(false);
  const [openFailed, setOpenFailed] = useState(false);

  const download = async () => {
    if (!apk.manifest?.downloadUrl) return;
    setOpening(true);
    setOpenFailed(false);
    try {
      await Linking.openURL(apk.manifest.downloadUrl);
    } catch {
      setOpenFailed(true);
    } finally {
      setOpening(false);
    }
  };

  if (apk.state === "required" && apk.manifest) {
    return (
      <View style={{ flex: 1, alignItems: "center", justifyContent: "center", padding: space.xxl, gap: space.md, backgroundColor: colors.surface }}>
        <Text style={{ fontSize: 22, fontWeight: "800", color: colors.text, textAlign: "center" }}>Update required</Text>
        <Text style={{ color: colors.textMuted, textAlign: "center", lineHeight: 22 }}>
          A new version of Veekay Partner is required to continue. Download and install the latest version ({apk.manifest.latestVersionName}).
        </Text>
        {apk.manifest.notes ? <Text style={{ color: colors.textFaint, textAlign: "center" }}>{apk.manifest.notes}</Text> : null}
        <Button title="Download update" onPress={() => void download()} loading={opening} style={{ alignSelf: "stretch", marginTop: space.sm }} />
        {openFailed ? <Text style={{ color: colors.danger, textAlign: "center" }}>Could not open the download link. Please try again.</Text> : null}
        <Text style={{ color: colors.textFaint, fontSize: 12, textAlign: "center", lineHeight: 18 }}>
          Open the downloaded file to install. If Android asks, allow installing apps from this source. Your data stays on the phone.
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
                  <Button title="Update now" onPress={() => void download()} loading={opening} style={{ flex: 1 }} />
                  <Button title="Later" variant="secondary" onPress={apk.dismiss} style={{ flex: 1 }} />
                </View>
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
