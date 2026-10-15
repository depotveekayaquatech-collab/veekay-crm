import { useEffect, useState } from "react";
import { Alert, Pressable, Text, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import * as Haptics from "expo-haptics";
import * as Location from "expo-location";
import { useQueryClient } from "@tanstack/react-query";
import { staffApi, type Reading } from "@/api/staff";
import { useAttendanceToday } from "@/api/staffHooks";
import { useAuth } from "@/auth/AuthProvider";
import { Badge, Card, ErrorNote, ListSkeleton, Screen, SectionTitle } from "@/components/ui";
import { fmtDate, niceName } from "@/lib/format";
import { useScanQueue } from "@/lib/useScanQueue";
import { colors, font, radius } from "@/theme";

const time = (iso: string) => new Date(iso).toLocaleTimeString("en-IN", { hour: "numeric", minute: "2-digit" });
const hm = (min: number) => `${Math.floor(min / 60)}h ${String(min % 60).padStart(2, "0")}m`;

/** The phone's position at this moment, or why we don't have one. Asked only when the person taps Check in / out. */
async function readLocation(): Promise<{ reading: Reading } | { skipped: "denied" | "unavailable" }> {
  let perm = await Location.getForegroundPermissionsAsync();
  if (!perm.granted && perm.canAskAgain) {
    await new Promise<void>((resolve) =>
      Alert.alert("Share your location?", "Veekay uses your location only at the moment you check in or out, to record where you were. It is never tracked in the background.", [{ text: "Continue", onPress: () => resolve() }]),
    );
    perm = await Location.requestForegroundPermissionsAsync();
  }
  if (!perm.granted) return { skipped: "denied" };
  try {
    const pos = await Promise.race([
      Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.High }),
      new Promise<never>((_, rej) => setTimeout(() => rej(new Error("timeout")), 15_000)),
    ]);
    return { reading: { latitude: pos.coords.latitude, longitude: pos.coords.longitude, accuracy: pos.coords.accuracy ?? undefined } };
  } catch {
    return { skipped: "unavailable" };
  }
}

function Action({ icon, label, onPress, tone }: { icon: React.ComponentProps<typeof Ionicons>["name"]; label: string; onPress: () => void; tone: [string, string] }) {
  return (
    <Pressable onPress={onPress} accessibilityRole="button" accessibilityLabel={label} android_ripple={{ color: colors.brand100 }}
      style={{ width: "48.5%", backgroundColor: colors.surface, borderRadius: radius.lg, borderWidth: 1, borderColor: colors.border, padding: 14, gap: 12 }}>
      <View style={{ width: 40, height: 40, borderRadius: radius.md, backgroundColor: tone[0], alignItems: "center", justifyContent: "center" }}>
        <Ionicons name={icon} size={21} color={tone[1]} />
      </View>
      <Text style={{ fontSize: 14, fontWeight: "700", color: colors.text }}>{label}</Text>
    </Pressable>
  );
}

export default function Today() {
  const { staff, hasPermission } = useAuth();
  const router = useRouter();
  const qc = useQueryClient();
  const q = useAttendanceToday();
  const queue = useScanQueue();
  const [busy, setBusy] = useState(false);
  const [, tick] = useState(0);

  useEffect(() => {
    const id = setInterval(() => tick((n) => n + 1), 30_000);   // keeps the running timer fresh
    return () => clearInterval(id);
  }, []);

  const a = q.data;
  const running = a?.checked_in && !a.checked_out && a.check_in_at ? Math.max(0, Math.round((Date.now() - new Date(a.check_in_at).getTime()) / 60000)) : null;

  async function press(kind: "in" | "out") {
    setBusy(true);
    try {
      const got = await readLocation();
      let reading: Reading = {};
      if ("reading" in got) reading = got.reading;
      else {
        const ok = await new Promise<boolean>((resolve) =>
          Alert.alert(
            got.skipped === "denied" ? "Location is off" : "Couldn't get your location",
            `You can still check ${kind} without it. It will be recorded as "location not shared".`,
            [{ text: "Cancel", style: "cancel", onPress: () => resolve(false) }, { text: `Check ${kind} anyway`, onPress: () => resolve(true) }],
          ),
        );
        if (!ok) return;
      }
      await (kind === "in" ? staffApi.checkIn(reading) : staffApi.checkOut(reading));
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success).catch(() => undefined);
      await qc.invalidateQueries({ queryKey: ["s-attendance"] });
    } catch (e) {
      Alert.alert("Couldn't record that", e instanceof Error ? e.message : "Please try again.");
    } finally {
      setBusy(false);
    }
  }

  const statusText = !a ? "" : a.on_leave ? "On leave today" : a.is_weekly_off && !a.checked_in ? "Weekly off" : !a.checked_in ? "Not checked in" : a.checked_out ? "Day complete" : "Working";
  const dot = !a ? colors.textFaint : a.checked_in && !a.checked_out ? colors.success : a.checked_out ? colors.brand600 : colors.warning;

  return (
    <Screen onRefresh={() => qc.invalidateQueries()} refreshing={q.isRefetching && !q.isLoading}>
      <Text style={font.small}>{fmtDate(new Date().toISOString().slice(0, 10))}</Text>
      <Text style={[font.title, { marginTop: 2 }]}>Hello, {niceName(staff?.full_name ?? "").split(" ")[0]}</Text>

      <View style={{ marginTop: 16 }}>
        {q.isLoading ? <ListSkeleton rows={2} /> : q.isError ? <ErrorNote message={q.error.message} onRetry={() => q.refetch()} /> : a && !a.eligible ? (
          <Card><Text style={font.small}>Attendance is not tracked for your role.</Text></Card>
        ) : a ? (
          <Card style={{ padding: 0, overflow: "hidden" }}>
            <View style={{ padding: 18, flexDirection: "row", alignItems: "center", gap: 10 }}>
              <View style={{ width: 10, height: 10, borderRadius: 5, backgroundColor: dot }} />
              <Text style={{ fontSize: 16, fontWeight: "800", color: colors.text, flex: 1 }}>{statusText}</Text>
              {a.late && a.checked_in ? <Badge tone="warning">Late</Badge> : null}
            </View>

            <View style={{ alignItems: "center", paddingVertical: 10 }}>
              <Text style={{ fontSize: 44, fontWeight: "800", letterSpacing: -1, color: colors.text }}>
                {running !== null ? hm(running) : a.checked_out && a.minutes !== null ? hm(a.minutes) : "--:--"}
              </Text>
              <Text style={font.small}>{running !== null ? "since you checked in" : a.checked_out ? "worked today" : `Work starts ${a.work_start}`}</Text>
            </View>

            <View style={{ flexDirection: "row", paddingHorizontal: 18, paddingVertical: 14, gap: 12 }}>
              <View style={{ flex: 1 }}><Text style={font.tiny}>CHECK IN</Text><Text style={{ fontWeight: "700", color: colors.text, marginTop: 2 }}>{a.check_in_at ? time(a.check_in_at) : "–"}</Text></View>
              <View style={{ flex: 1 }}><Text style={font.tiny}>CHECK OUT</Text><Text style={{ fontWeight: "700", color: colors.text, marginTop: 2 }}>{a.check_out_at ? time(a.check_out_at) : "–"}</Text></View>
              <View style={{ flex: 1 }}>
                <Text style={font.tiny}>LOCATION</Text>
                <Text numberOfLines={2} style={{ fontWeight: "700", color: a.check_in_location?.status === "office" ? colors.success : colors.warning, marginTop: 2 }}>{a.check_in_location?.status === "office" ? (a.check_in_location.label ?? "Office") : a.checked_in ? "Away (not from office)" : "–"}</Text>
              </View>
            </View>

            {!a.checked_out && !a.on_leave ? (
              <View style={{ padding: 16, paddingTop: 4 }}>
                <Pressable
                  onPress={() => press(a.checked_in ? "out" : "in")}
                  disabled={busy}
                  accessibilityRole="button"
                  accessibilityLabel={a.checked_in ? "Check out" : "Check in"}
                  style={{ height: 58, borderRadius: radius.lg, backgroundColor: a.checked_in ? colors.danger : colors.brand600, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 10, opacity: busy ? 0.6 : 1 }}
                >
                  <Ionicons name={a.checked_in ? "log-out-outline" : "log-in-outline"} size={22} color="#fff" />
                  <Text style={{ color: "#fff", fontSize: 17, fontWeight: "800" }}>{busy ? "Getting location…" : a.checked_in ? "Check out" : "Check in"}</Text>
                </Pressable>
              </View>
            ) : null}
          </Card>
        ) : null}
      </View>

      {queue.pending.length > 0 && (
        <Pressable onPress={() => router.push("/staff/sync")} accessibilityRole="button" style={{ marginTop: 14, flexDirection: "row", alignItems: "center", gap: 10, padding: 14, borderRadius: radius.md, backgroundColor: colors.warningSoft }}>
          <Ionicons name="cloud-offline-outline" size={20} color={colors.warning} />
          <Text style={{ flex: 1, color: colors.warning, fontWeight: "700" }}>{queue.pending.length} bottle scan{queue.pending.length === 1 ? "" : "s"} waiting to sync</Text>
          <Ionicons name="chevron-forward" size={18} color={colors.warning} />
        </Pressable>
      )}

      <SectionTitle>Quick actions</SectionTitle>
      <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 12 }}>
        {hasPermission("orders.mark") && <Action icon="create-outline" label="Mark orders" onPress={() => router.push("/staff/orders")} tone={[colors.brand50, colors.brand600]} />}
        {hasPermission("bottles.scan") && <Action icon="qr-code-outline" label="Scan bottles" onPress={() => router.push("/staff/scan")} tone={[colors.successSoft, colors.success]} />}
        {hasPermission("cash.add") && <Action icon="wallet-outline" label="Add expense" onPress={() => router.push("/staff/expense/new")} tone={[colors.warningSoft, colors.warning]} />}
        <Action icon="calendar-outline" label="Leave" onPress={() => router.push("/staff/leave")} tone={[colors.dangerSoft, colors.danger]} />
      </View>
    </Screen>
  );
}
