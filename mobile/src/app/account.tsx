import { Alert, Linking, Pressable, Text, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import Constants from "expo-constants";
import { useRouter } from "expo-router";
import { useAuth } from "@/auth/AuthProvider";
import { Button, Card, Screen, SectionTitle } from "@/components/ui";
import { niceName } from "@/lib/format";
import { colors, font } from "@/theme";

const extra = (Constants.expoConfig?.extra ?? {}) as { privacyPolicyUrl?: string; supportEmail?: string; supportPhone?: string };

function LinkRow({ icon, label, onPress }: { icon: React.ComponentProps<typeof Ionicons>["name"]; label: string; onPress: () => void }) {
  return (
    <Pressable onPress={onPress} accessibilityRole="button" android_ripple={{ color: colors.brand100 }} style={{ minHeight: 54, paddingHorizontal: 16, flexDirection: "row", alignItems: "center", gap: 12, borderTopWidth: 1, borderTopColor: colors.border }}>
      <Ionicons name={icon} size={20} color={colors.brand600} />
      <Text style={{ flex: 1, fontSize: 15, fontWeight: "600", color: colors.text }}>{label}</Text>
      <Ionicons name="chevron-forward" size={18} color={colors.textFaint} />
    </Pressable>
  );
}

export default function Account() {
  const { account, signOut } = useAuth();
  const router = useRouter();
  if (!account) return null;

  const rows: [string, string][] = [
    ["Name", niceName(account.full_name)],
    ["Type", account.kind === "vendor" ? "Vendor" : "Store POC"],
    ["Login", account.email],
    ["Phone", account.phone ?? "–"],
    ["Platforms", account.platforms.map((p) => p[0].toUpperCase() + p.slice(1)).join(", ") || "–"],
    ["Stores", String(account.store_count)],
  ];

  function requestDeletion() {
    Alert.alert(
      "Request data deletion",
      "We will email Veekay support to remove your login and the data tied to it. Records Veekay must keep (orders, bills, compliance documents) are retained.",
      [
        { text: "Cancel", style: "cancel" },
        {
          text: "Send request",
          onPress: () => {
            const to = extra.supportEmail || "";
            const subject = encodeURIComponent("Account and data deletion request");
            const body = encodeURIComponent(`Please delete my Veekay Partner login.\n\nLogin: ${account!.email}`);
            Linking.openURL(`mailto:${to}?subject=${subject}&body=${body}`).catch(() => Alert.alert("No email app", "Please write to Veekay support to request deletion."));
          },
        },
      ],
    );
  }

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

      <SectionTitle>More</SectionTitle>
      <Card style={{ padding: 0, overflow: "hidden" }}>
        <LinkRow icon="car-outline" label="Delivery history" onPress={() => router.push("/deliveries")} />
        <LinkRow icon="cube-outline" label="Bottles at my stores" onPress={() => router.push("/bottles")} />
        <LinkRow icon="storefront-outline" label="My stores" onPress={() => router.push("/stores")} />
      </Card>

      <SectionTitle>Help and privacy</SectionTitle>
      <Card style={{ padding: 0, overflow: "hidden" }}>
        {extra.supportPhone ? <LinkRow icon="call-outline" label={`Call support  ${extra.supportPhone}`} onPress={() => Linking.openURL(`tel:${extra.supportPhone}`)} /> : null}
        {extra.supportEmail ? <LinkRow icon="mail-outline" label="Email support" onPress={() => Linking.openURL(`mailto:${extra.supportEmail}`)} /> : null}
        {extra.privacyPolicyUrl ? <LinkRow icon="shield-checkmark-outline" label="Privacy policy" onPress={() => Linking.openURL(extra.privacyPolicyUrl!)} /> : null}
        <LinkRow icon="trash-outline" label="Request data deletion" onPress={requestDeletion} />
      </Card>

      <Button title="Sign out" variant="secondary" onPress={() => Alert.alert("Sign out?", "You will need your login and password to sign in again.", [{ text: "Cancel", style: "cancel" }, { text: "Sign out", style: "destructive", onPress: () => void signOut() }])} style={{ marginTop: 28 }} />
      <Text style={[font.tiny, { textAlign: "center", marginTop: 16 }]}>Veekay Partner · version {Constants.expoConfig?.version ?? "1.0.0"}</Text>
    </Screen>
  );
}
