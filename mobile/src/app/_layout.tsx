import { useEffect, useState } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Stack, useRouter } from "expo-router";
import * as Notifications from "expo-notifications";
import * as SplashScreen from "expo-splash-screen";
import { StatusBar } from "expo-status-bar";
import { SafeAreaProvider } from "react-native-safe-area-context";
import { Text, View } from "react-native";
import { AuthProvider, useAuth } from "@/auth/AuthProvider";
import { configError } from "@/api/client";
import { registerPush } from "@/lib/push";
import { startAutoFlush } from "@/lib/scanQueue";
import { connectOnlineManager, useDailyRefresh } from "@/lib/dailyRefresh";
import { installGlobalErrorHandler, reportError } from "@/lib/crash";
import { Pressable } from "react-native";
import { colors } from "@/theme";

SplashScreen.preventAutoHideAsync().catch(() => undefined);
connectOnlineManager();
installGlobalErrorHandler();

/** Shown instead of a blank screen when a screen crashes. Expo Router uses this export automatically. */
export function ErrorBoundary({ error, retry }: { error: Error; retry: () => Promise<void> }) {
  useEffect(() => { void reportError(error, { fatal: false, screen: "boundary" }); }, [error]);
  return (
    <View style={{ flex: 1, alignItems: "center", justifyContent: "center", padding: 32, gap: 12, backgroundColor: colors.surface }}>
      <Text style={{ fontSize: 20, fontWeight: "800", color: colors.text, textAlign: "center" }}>Something went wrong</Text>
      <Text style={{ color: colors.textMuted, textAlign: "center", lineHeight: 21 }}>The problem has been reported. Your saved bottle scans are safe on this phone.</Text>
      <Pressable onPress={() => void retry()} accessibilityRole="button" style={{ marginTop: 8, minHeight: 50, paddingHorizontal: 28, borderRadius: 12, backgroundColor: colors.brand600, alignItems: "center", justifyContent: "center" }}>
        <Text style={{ color: colors.white, fontWeight: "800", fontSize: 16 }}>Try again</Text>
      </Pressable>
    </View>
  );
}

const header = {
  headerStyle: { backgroundColor: colors.surface },
  headerTintColor: colors.brand600,
  headerTitleStyle: { color: colors.text, fontWeight: "700" as const },
  headerShadowVisible: false,
  contentStyle: { backgroundColor: colors.surfaceSubtle },
};

function Navigator() {
  const { account, staff, loading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!loading) SplashScreen.hideAsync().catch(() => undefined);
  }, [loading]);

  // Ask for the notification permission and register for push right after sign-in.
  useEffect(() => {
    if (account) void registerPush("partner");
  }, [account]);
  useEffect(() => {
    if (staff && !staff.must_change_password) void registerPush("staff");
  }, [staff]);

  // An employee's offline bottle scans are sent as soon as the phone has a connection again.
  const staffReady = !!staff && !staff.must_change_password;
  useEffect(() => (staffReady ? startAutoFlush() : undefined), [staffReady]);

  // Re-read everything from the CRM when the app opens after the daily 10:00 sync has run.
  useDailyRefresh(!!account || staffReady);

  // Tapping a push opens the ticket it is about.
  useEffect(() => {
    const open = (data: Record<string, unknown> | undefined) => {
      const ref = typeof data?.ref_id === "string" && data.ref_id ? data.ref_id : null;
      if (data?.audience === "staff") {
        // an employee's alert: leave goes to the approvals list for reviewers, everything else to the alerts list
        router.push(data.kind === "leave" ? "/staff/leave" : "/staff/alerts");
      } else if (data?.kind === "ticket" && ref) router.push(`/tickets/${ref}`);
      else if (data?.kind === "bill") router.push({ pathname: "/documents", params: { kind: "bill" } });
    };
    const sub = Notifications.addNotificationResponseReceivedListener((r) => open(r.notification.request.content.data));
    const last = Notifications.getLastNotificationResponse();
    if (last) open(last.notification.request.content.data);
    return () => sub.remove();
  }, [router]);

  if (loading) return null;

  return (
    <Stack screenOptions={header}>
      <Stack.Protected guard={!!account}>
        <Stack.Screen name="(tabs)" options={{ headerShown: false }} />
        <Stack.Screen name="tickets/new" options={{ title: "Raise a ticket" }} />
        <Stack.Screen name="tickets/[id]" options={{ title: "Ticket" }} />
        <Stack.Screen name="documents/upload" options={{ title: "Upload a document" }} />
        <Stack.Screen name="deliveries/index" options={{ title: "Deliveries" }} />
        <Stack.Screen name="deliveries/new" options={{ title: "Confirm a delivery" }} />
        <Stack.Screen name="stores" options={{ title: "Your stores" }} />
        <Stack.Screen name="bottles" options={{ title: "Bottles at your stores" }} />
        <Stack.Screen name="account" options={{ title: "Account" }} />
      </Stack.Protected>
      <Stack.Protected guard={staffReady}>
        <Stack.Screen name="staff/(tabs)" options={{ headerShown: false }} />
        <Stack.Screen name="staff/mark/[storeId]" options={{ title: "Mark orders" }} />
        <Stack.Screen name="staff/expense/new" options={{ title: "Add a purchase" }} />
        <Stack.Screen name="staff/leave/index" options={{ title: "Leave" }} />
        <Stack.Screen name="staff/leave/new" options={{ title: "Apply for leave" }} />
        <Stack.Screen name="staff/sync" options={{ title: "Scan sync" }} />
        <Stack.Screen name="staff/alerts" options={{ title: "Alerts" }} />
        <Stack.Screen name="staff/admin/pending" options={{ title: "Stores yet to mark" }} />
        <Stack.Screen name="staff/admin/leaves" options={{ title: "Leave approvals" }} />
        <Stack.Screen name="staff/admin/bottles" options={{ title: "Overdue bottles" }} />
        <Stack.Screen name="staff/admin/bills" options={{ title: "Bills past due" }} />
        <Stack.Screen name="staff/me" options={{ title: "Profile" }} />
      </Stack.Protected>
      <Stack.Protected guard={!!staff && staff.must_change_password}>
        <Stack.Screen name="staff/change-password" options={{ headerShown: false }} />
      </Stack.Protected>
      <Stack.Protected guard={!account && !staff}>
        <Stack.Screen name="login" options={{ headerShown: false }} />
      </Stack.Protected>
    </Stack>
  );
}

export default function RootLayout() {
  const [client] = useState(() => new QueryClient({ defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } } }));

  if (configError) {
    return (
      <View style={{ flex: 1, alignItems: "center", justifyContent: "center", padding: 32, backgroundColor: colors.surface }}>
        <Text style={{ fontSize: 18, fontWeight: "700", color: colors.text, textAlign: "center" }}>App setup incomplete</Text>
        <Text style={{ marginTop: 8, color: colors.textMuted, textAlign: "center" }}>{configError}</Text>
      </View>
    );
  }

  return (
    <SafeAreaProvider>
      <QueryClientProvider client={client}>
        <AuthProvider>
          <StatusBar style="dark" />
          <Navigator />
        </AuthProvider>
      </QueryClientProvider>
    </SafeAreaProvider>
  );
}
