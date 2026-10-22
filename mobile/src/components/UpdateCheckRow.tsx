import { useState } from "react";
import { ActivityIndicator, Alert, Pressable, Text } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import Constants from "expo-constants";
import { useAuth } from "@/auth/AuthProvider";
import { currentApkUpdate, installedVersionCode, refreshApkManifest, showUpdateAgain } from "@/lib/appUpdates";
import { colors } from "@/theme";

/** "Version 1.0.1 (build 8)" for the footer of the profile screens. */
export const versionLabel = () => `version ${Constants.expoConfig?.version ?? "1.0.0"} (build ${installedVersionCode() || "?"})`;

/** Checks for a newer APK right now, whatever the 10-minute timer says, and says plainly what it found. */
export function UpdateCheckRow() {
  const [busy, setBusy] = useState(false);
  const { account, staff } = useAuth();
  const audience = staff ? "staff" : account ? "partner" : null;

  async function check() {
    if (busy) return;
    setBusy(true);
    try {
      if (!(await refreshApkManifest())) {
        Alert.alert("Couldn't check for updates", "Check your internet connection and try again.");
        return;
      }
      const { state, manifest } = currentApkUpdate(audience);
      if (state !== "none" && manifest) {
        showUpdateAgain();
        Alert.alert("Update available", `Version ${manifest.latestVersionName} is ready. Tap "Update now" in the box at the bottom of the screen.`);
      } else if (manifest && installedVersionCode() < manifest.latestVersionCode) {
        Alert.alert("Update on its way", "A newer version exists but its download is not ready yet. Please try again later.");
      } else {
        Alert.alert("You're up to date", `You have the latest ${versionLabel()}.`);
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <Pressable onPress={() => void check()} disabled={busy} accessibilityRole="button" android_ripple={{ color: colors.brand100 }}
      style={{ minHeight: 54, paddingHorizontal: 16, flexDirection: "row", alignItems: "center", gap: 12, borderTopWidth: 1, borderTopColor: colors.border }}>
      <Ionicons name="cloud-download-outline" size={20} color={colors.brand600} />
      <Text style={{ flex: 1, fontSize: 15, fontWeight: "600", color: colors.text }}>Check for updates</Text>
      {busy ? <ActivityIndicator color={colors.brand600} /> : <Ionicons name="chevron-forward" size={18} color={colors.textFaint} />}
    </Pressable>
  );
}
