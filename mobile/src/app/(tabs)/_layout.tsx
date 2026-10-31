import { Pressable, Text, View, type ColorValue } from "react-native";
import { Tabs, useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useAuth } from "@/auth/AuthProvider";
import { useNotifications } from "@/api/hooks";
import { niceName } from "@/lib/format";
import { colors } from "@/theme";

type IconName = React.ComponentProps<typeof Ionicons>["name"];
/** The icon sits in a soft pill while its tab is open, so the current tab reads at a glance. */
const icon = (name: IconName, focused: IconName) => ({ color, focused: f, size }: { color: ColorValue; focused: boolean; size: number }) => (
  <View style={{ width: 56, height: 30, borderRadius: 15, alignItems: "center", justifyContent: "center", backgroundColor: f ? colors.brand50 : "transparent" }}>
    <Ionicons name={f ? focused : name} size={size} color={color} />
  </View>
);

export default function TabsLayout() {
  const { account } = useAuth();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const { data } = useNotifications();

  return (
    <Tabs
      screenOptions={{
        headerStyle: { backgroundColor: colors.surface },
        headerShadowVisible: false,
        headerTitleStyle: { color: colors.text, fontWeight: "800" },
        headerRight: () => (
          <Pressable
            onPress={() => router.push("/account")}
            accessibilityRole="button"
            accessibilityLabel="Account"
            hitSlop={8}
            style={({ pressed }) => ({ marginRight: 16, width: 36, height: 36, borderRadius: 18, backgroundColor: colors.brand600, alignItems: "center", justifyContent: "center", borderWidth: 2, borderColor: colors.brand100, opacity: pressed ? 0.85 : 1 })}
          >
            <Text style={{ color: colors.white, fontWeight: "700" }}>{niceName(account?.full_name ?? "?").trim().slice(0, 1).toUpperCase()}</Text>
          </Pressable>
        ),
        tabBarActiveTintColor: colors.brand600,
        tabBarInactiveTintColor: colors.textFaint,
        tabBarLabelStyle: { fontSize: 11, fontWeight: "600" },
        tabBarStyle: { backgroundColor: colors.surface, borderTopColor: colors.border, height: 62 + insets.bottom, paddingBottom: insets.bottom + 4, paddingTop: 6, elevation: 8, shadowColor: "#0B1222", shadowOpacity: 0.08, shadowRadius: 10, shadowOffset: { width: 0, height: -2 } },
        sceneStyle: { backgroundColor: colors.surfaceSubtle },
      }}
    >
      <Tabs.Screen name="index" options={{ title: "Home", headerTitle: "Aquatrack", tabBarIcon: icon("home-outline", "home") }} />
      <Tabs.Screen name="orders" options={{ title: "Orders", tabBarIcon: icon("cube-outline", "cube") }} />
      <Tabs.Screen name="tickets" options={{ title: "Tickets", tabBarIcon: icon("ticket-outline", "ticket") }} />
      <Tabs.Screen name="documents" options={{ title: "Documents", tabBarIcon: icon("document-text-outline", "document-text") }} />
      <Tabs.Screen
        name="alerts"
        options={{ title: "Alerts", tabBarIcon: icon("notifications-outline", "notifications"), tabBarBadge: data?.unread ? (data.unread > 9 ? "9+" : data.unread) : undefined, tabBarBadgeStyle: { backgroundColor: colors.danger } }}
      />
    </Tabs>
  );
}
