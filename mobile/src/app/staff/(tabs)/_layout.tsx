import { useState } from "react";
import { Pressable, Text, View, type ColorValue } from "react-native";
import { Tabs, useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { useAuth } from "@/auth/AuthProvider";
import { useAttendanceToday, useStaffAlerts } from "@/api/staffHooks";
import { MenuDrawer, type MenuSection } from "@/components/MenuDrawer";
import { SalaryReceivedModal } from "@/components/SalaryReceivedModal";
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
  const waiting = useScanQueue().pending.length;
  const unread = useStaffAlerts().data?.unread ?? 0;
  const eligibleForAttendance = useAttendanceToday().data?.eligible ?? false;
  const [menuOpen, setMenuOpen] = useState(false);

  // The same permissions the web CRM's Compliance tab and the server use. The server checks them again on every request.
  const canCompliance = hasPermission("compliance.upload") || hasPermission("compliance.manage");

  // Employees always open on Today, so Check in / Check out is the first thing they see. Only admins who can see the order
  // overview open on Insights (the Admin tab).
  const landsOnInsights = hasPermission("orders.overview");

  const canAdminTab = ["orders.overview", "leave.review", "bottles.view", "accounts.view"].some(hasPermission);
  const canExpenses = hasPermission("cash.add") || hasPermission("cash.view");

  // Every screen in one menu (the three-line button): the main areas first, then the rest. Same permissions as before.
  const sections: MenuSection[] = [
    {
      items: [
        { key: "today", label: "Today", icon: "today-outline", href: "/staff", path: "/staff" },
        ...(hasPermission("orders.mark") ? [{ key: "orders", label: "Orders", icon: "create-outline" as IconName, href: "/staff/orders" as const, path: "/staff/orders" }] : []),
        ...(hasPermission("bottles.scan") ? [{ key: "scan", label: "Scan bottles", icon: "qr-code-outline" as IconName, href: "/staff/scan" as const, path: "/staff/scan", badge: waiting }] : []),
        ...(canCompliance ? [{ key: "compliance", label: "Compliance", icon: "shield-checkmark-outline" as IconName, href: "/staff/compliance" as const, path: "/staff/compliance" }] : []),
        ...(canAdminTab ? [{ key: "admin", label: landsOnInsights ? "Insights" : "Admin", icon: "stats-chart-outline" as IconName, href: "/staff/admin" as const, path: "/staff/admin" }] : []),
        ...(canExpenses ? [{ key: "cash", label: "Expenses", icon: "wallet-outline" as IconName, href: "/staff/cash" as const, path: "/staff/cash" }] : []),
      ],
    },
    {
      title: "More",
      items: [
        ...(canCompliance ? [{ key: "cards", label: "Store cards", icon: "id-card-outline" as IconName, href: "/staff/cards" as const, path: "/staff/cards" }] : []),
        ...(eligibleForAttendance ? [{ key: "payslips", label: "Payslips", icon: "cash-outline" as IconName, href: "/staff/payslips" as const, path: "/staff/payslips" }] : []),
        ...(hasPermission("orders.view") ? [{ key: "inventory", label: "Inventory", icon: "storefront-outline" as IconName, href: "/staff/inventory" as never, path: "/staff/inventory" }] : []),
        ...(hasPermission("orders.view") && !hasPermission("orders.overview") ? [{ key: "myperf", label: staff?.entry_level === "team_lead" ? "Team performance" : "My performance", icon: "speedometer-outline" as IconName, href: "/staff/performance" as never, path: "/staff/performance" }] : []),
        ...(hasPermission("orders.view") ? [{ key: "vendors", label: "Vendor performance", icon: "business-outline" as IconName, href: "/staff/vendors" as never, path: "/staff/vendors" }] : []),
        ...(hasPermission("orders.mark") ? [{ key: "entries", label: "My entries", icon: "checkmark-done-outline" as IconName, href: "/staff/entries" as const, path: "/staff/entries" }] : []),
        { key: "leave", label: "Leave", icon: "calendar-outline" as IconName, href: "/staff/leave" as const, path: "/staff/leave" },
        { key: "alerts", label: "Alerts", icon: "notifications-outline" as IconName, href: "/staff/alerts" as const, path: "/staff/alerts", badge: unread },
        { key: "me", label: "Profile", icon: "person-circle-outline" as IconName, href: "/staff/me" as const, path: "/staff/me" },
      ],
    },
  ];

  return (
    <>
    <Tabs
      initialRouteName={staff?.is_admin && landsOnInsights ? "admin" : "index"}
      screenOptions={{
        headerStyle: { backgroundColor: colors.surface },
        headerShadowVisible: false,
        headerTitleAlign: "center",
        headerTitleStyle: { color: colors.text, fontWeight: "800" },
        headerLeft: () => (
          <Pressable onPress={() => setMenuOpen(true)} accessibilityRole="button" accessibilityLabel={waiting ? `Menu, ${waiting} scans waiting` : "Menu"} hitSlop={6}
            style={({ pressed }) => ({ marginLeft: 12, width: 40, height: 40, borderRadius: 20, alignItems: "center", justifyContent: "center", backgroundColor: pressed ? colors.surfaceMuted : colors.surfaceSubtle })}>
            <Ionicons name="menu" size={24} color={colors.text} />
            {waiting > 0 && <View style={{ position: "absolute", top: 5, right: 5, width: 10, height: 10, borderRadius: 5, backgroundColor: colors.warning, borderWidth: 1.5, borderColor: colors.surface }} />}
          </Pressable>
        ),
        headerRight: () => (
          <View style={{ flexDirection: "row", alignItems: "center", gap: 10, marginRight: 12 }}>
            <Pressable onPress={() => router.push("/staff/alerts")} accessibilityRole="button" accessibilityLabel={unread ? `Alerts, ${unread} unread` : "Alerts"} hitSlop={6}
              style={({ pressed }) => ({ width: 40, height: 40, borderRadius: 20, alignItems: "center", justifyContent: "center", backgroundColor: pressed ? colors.surfaceMuted : colors.surfaceSubtle })}>
              <Ionicons name={unread ? "notifications" : "notifications-outline"} size={22} color={colors.text} />
              {unread > 0 && (
                <View style={{ position: "absolute", top: 2, right: 0, minWidth: 18, height: 18, borderRadius: 9, paddingHorizontal: 4, backgroundColor: colors.danger, alignItems: "center", justifyContent: "center", borderWidth: 1.5, borderColor: colors.surface }}>
                  <Text style={{ color: colors.white, fontSize: 10, fontWeight: "800" }}>{unread > 9 ? "9+" : unread}</Text>
                </View>
              )}
            </Pressable>
            <Pressable onPress={() => router.push("/staff/me")} accessibilityRole="button" accessibilityLabel="Profile" hitSlop={6}
              style={({ pressed }) => ({ width: 40, height: 40, borderRadius: 20, backgroundColor: colors.brand600, alignItems: "center", justifyContent: "center", borderWidth: 2, borderColor: colors.brand100, opacity: pressed ? 0.85 : 1 })}>
              <Text style={{ color: colors.white, fontWeight: "700" }}>{niceName(staff?.full_name ?? "?").trim().slice(0, 1).toUpperCase()}</Text>
            </Pressable>
          </View>
        ),
        tabBarActiveTintColor: colors.brand600,
        tabBarInactiveTintColor: colors.textFaint,
        tabBarLabelStyle: { fontSize: 10.5, fontWeight: "600" },
        tabBarStyle: { display: "none" },   // navigation lives in the menu (three-line button), so there is no second bar to repeat it
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
        name="compliance"
        options={{ title: "Compliance", headerTitle: "Compliance", href: canCompliance ? undefined : null, tabBarIcon: icon("shield-checkmark-outline", "shield-checkmark") }}
      />
      <Tabs.Screen
        name="admin"
        options={{ title: landsOnInsights ? "Insights" : "Admin", headerTitle: landsOnInsights ? "Insights" : "Admin", href: ["orders.overview", "leave.review", "bottles.view", "accounts.view"].some(hasPermission) ? undefined : null, tabBarIcon: icon("stats-chart-outline", "stats-chart") }}
      />
      <Tabs.Screen name="cash" options={{ title: "Expenses", href: hasPermission("cash.add") || hasPermission("cash.view") ? undefined : null, tabBarIcon: icon("wallet-outline", "wallet") }} />
    </Tabs>
    <SalaryReceivedModal />   {/* "Salary received": shown on whichever main screen is open, checked every minute */}
    <MenuDrawer open={menuOpen} onClose={() => setMenuOpen(false)} sections={sections} who={{ name: niceName(staff?.full_name ?? ""), code: staff?.employee_code ?? "" }} />
    </>
  );
}
