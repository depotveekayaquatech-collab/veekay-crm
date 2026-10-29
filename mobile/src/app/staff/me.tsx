import { Alert, Linking, Pressable, Text, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import Constants from "expo-constants";
import { useRouter } from "expo-router";
import { useAuth } from "@/auth/AuthProvider";
import { Button, Card, Screen, SectionTitle } from "@/components/ui";
import { AppearanceCard } from "@/components/AppearanceCard";
import { SyncCard } from "@/components/SyncCard";
import { niceName } from "@/lib/format";
import { UpdateCheckRow, versionLabel } from "@/components/UpdateCheckRow";
import { colors, font } from "@/theme";

// The level on the profile; the server sends the label itself, this covers a server that is a version behind.
const LEVEL_LABEL: Record<string, string> = { entry_contributor: "L1 Employee", team_lead: "L2 Team Lead", entry_reviewer: "L3 Entry Reviewer", administrator: "L4 Administrator" };

const extra = (Constants.expoConfig?.extra ?? {}) as { privacyPolicyUrl?: string; supportEmail?: string; supportPhone?: string };

function Row({ icon, label, onPress }: { icon: React.ComponentProps<typeof Ionicons>["name"]; label: string; onPress: () => void }) {
  return (
    <Pressable onPress={onPress} accessibilityRole="button" android_ripple={{ color: colors.brand100 }} style={{ minHeight: 54, paddingHorizontal: 16, flexDirection: "row", alignItems: "center", gap: 12, borderTopWidth: 1, borderTopColor: colors.border }}>
      <Ionicons name={icon} size={20} color={colors.brand600} />
      <Text style={{ flex: 1, fontSize: 15, fontWeight: "600", color: colors.text }}>{label}</Text>
      <Ionicons name="chevron-forward" size={18} color={colors.textFaint} />
    </Pressable>
  );
}

export default function Me() {
  const { staff, signOut } = useAuth();
  const router = useRouter();
  if (!staff) return null;
  const rows: [string, string][] = [
    ["Name", niceName(staff.full_name)],
    ["Employee ID", staff.employee_code],
    ["Level", staff.entry_level_label ?? LEVEL_LABEL[staff.entry_level ?? ""] ?? "L1 Employee"],
    ["Platform", staff.platform_label ?? "–"],
    ["Region", staff.region_name ?? "–"],
  ];
  return (
    <Screen>
      <Card style={{ padding: 0, overflow: "hidden" }}>
        {rows.map(([k, v], i) => (
          <View key={k} style={{ flexDirection: "row", justifyContent: "space-between", gap: 16, paddingHorizontal: 16, paddingVertical: 14, borderTopWidth: i ? 1 : 0, borderTopColor: colors.border }}>
            <Text style={font.small}>{k}</Text>
            <Text numberOfLines={1} style={{ flex: 1, textAlign: "right", fontWeight: "600", color: colors.text }}>{v}</Text>
          </View>
        ))}
      </Card>

      <View style={{ marginTop: 16 }}><SyncCard /></View>

      <SectionTitle>Shortcuts</SectionTitle>
      <Card style={{ padding: 0, overflow: "hidden" }}>
        <Row icon="calendar-outline" label="Leave" onPress={() => router.push("/staff/leave")} />
        <Row icon="cloud-upload-outline" label="Scan sync status" onPress={() => router.push("/staff/sync")} />
      </Card>

      <SectionTitle>Appearance</SectionTitle>
      <AppearanceCard />

      <SectionTitle>Help and privacy</SectionTitle>
      <Card style={{ padding: 0, overflow: "hidden" }}>
        {extra.supportPhone ? <Row icon="call-outline" label={`Call support  ${extra.supportPhone}`} onPress={() => Linking.openURL(`tel:${extra.supportPhone}`)} /> : null}
        {extra.supportEmail ? <Row icon="mail-outline" label="Email support" onPress={() => Linking.openURL(`mailto:${extra.supportEmail}`)} /> : null}
        {extra.privacyPolicyUrl ? <Row icon="shield-checkmark-outline" label="Privacy policy" onPress={() => Linking.openURL(extra.privacyPolicyUrl!)} /> : null}
        <UpdateCheckRow />
      </Card>

      <Button title="Sign out" variant="secondary" onPress={() => Alert.alert("Sign out?", "Scans waiting to sync stay on this phone and are sent after you sign in again.", [{ text: "Cancel", style: "cancel" }, { text: "Sign out", style: "destructive", onPress: () => void signOut() }])} style={{ marginTop: 28 }} />
      <Text style={[font.tiny, { textAlign: "center", marginTop: 16 }]}>Veekay · {versionLabel()}</Text>
    </Screen>
  );
}
