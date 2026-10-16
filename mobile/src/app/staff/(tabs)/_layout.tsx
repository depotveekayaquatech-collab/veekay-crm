import { Pressable, Text, View, type ColorValue } from "react-native";
import { Tabs, useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useAuth } from "@/auth/AuthProvider";
import { useStaffAlerts } from "@/api/staffHooks";
import { useScanQueue } from "@/lib/useScanQueue";
import { niceName } from "@/lib/format";
import { colors } from "@/theme";

type IconName = React.ComponentProps<typeof Ionicons>["name"];
const icon = (name: IconName, focused: IconName) => ({ color, focused: f, size }: { color: ColorValue; focused: boolean; size: number }) => (
  <Ionicons name={f ? focused : name} size={size} color={color} />
);

export default function StaffTabs() {
  const { staff, hasPermission } = useAuth();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const waiting = useScanQueue().pending.length;
  const unread = useStaffAlerts().data?.unread ?? 0;

  // People who can see the order overview land on Insights (the Admin tab); everyone else on Today.
  const landsOnInsights = hasPermission("orders.overview");

  return (
    <Tabs
      initialRouteName={landsOnInsights ? "admin" : "index"}
      screenOptions={{
        headerStyle: { backgroundColor: colors.surface },
        headerShadowVisible: false,
        headerTitleStyle: { color: colors.text, fontWeight: "700" },
        headerRight: () => (
          <View style={{ flexDirection: "row", alignItems: "center", gap: 14, marginRight: 16 }}>
            <Pressable onPress={() => router.push("/staff/alerts")} accessibilityRole="button" accessibilityLabel={unread ? `Alerts, ${unread} unread` : "Alerts"} hitSlop={8}>
              <Ionicons name={unread ? "notifications" : "notifications-outline"} size={24} color={colors.text} />
              {unread > 0 && (
                <View style={{ position: "absolute", top: -4, right: -6, minWidth: 16, height: 16, borderRadius: 8, paddingHorizontal: 3, backgroundColor: colors.danger, alignItems: "center", justifyContent: "center" }}>
                  <Text style={{ color: colors.white, fontSize: 10, fontWeight: "800" }}>{unread > 9 ? "9+" : unread}</Text>
                </View>
              )}
            </Pressable>
            <Pressable onPress={() => router.push("/staff/me")} accessibilityRole="button" accessibilityLabel="Profile" hitSlop={8}
              style={{ width: 36, height: 36, borderRadius: 18, backgroundColor: colors.brand600, alignItems: "center", justifyContent: "center" }}>
              <Text style={{ color: colors.white, fontWeight: "700" }}>{niceName(staff?.full_name ?? "?").trim().slice(0, 1).toUpperCase()}</Text>
            </Pressable>
          </View>
        ),
        tabBarActiveTintColor: colors.brand600,
        tabBarInactiveTintColor: colors.textFaint,
        tabBarLabelStyle: { fontSize: 11, fontWeight: "600" },
        tabBarStyle: { backgroundColor: colors.surface, borderTopColor: colors.border, height: 58 + insets.bottom, paddingBottom: insets.bottom + 4, paddingTop: 6 },
        sceneStyle: { backgroundColor: colors.surfaceSubtle },
      }}
    >
      <Tabs.Screen name="index" options={{ title: "Today", headerTitle: "Veekay", tabBarIcon: icon("today-outline", "today") }} />
      <Tabs.Screen name="orders" options={{ title: "Orders", href: hasPermission("orders.mark") ? undefined : null, tabBarIcon: icon("create-outline", "create") }} />
      <Tabs.Screen
        name="scan"
        options={{ title: "Scan", href: hasPermission("bottles.scan") ? undefined : null, tabBarIcon: icon("qr-code-outline", "qr-code"), tabBarBadge: waiting ? waiting : undefined, tabBarBadgeStyle: { backgroundColor: colors.warning } }}
      />
      <Tabs.Screen
        name="admin"
        options={{ title: landsOnInsights ? "Insights" : "Admin", headerTitle: landsOnInsights ? "Insights" : "Admin", href: ["orders.overview", "leave.review", "bottles.view", "accounts.view"].some(hasPermission) ? undefined : null, tabBarIcon: icon("stats-chart-outline", "stats-chart") }}
      />
      <Tabs.Screen name="cash" options={{ title: "Expenses", href: hasPermission("cash.add") || hasPermission("cash.view") ? undefined : null, tabBarIcon: icon("wallet-outline", "wallet") }} />
    </Tabs>
  );
}
