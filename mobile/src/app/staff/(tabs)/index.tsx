import { useEffect, useState } from "react";
import { Alert, Linking, Pressable, Text, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import * as Haptics from "expo-haptics";
import { useQueryClient } from "@tanstack/react-query";
import { staffApi, type Reading } from "@/api/staff";
import { describeFailure, readLocation } from "@/lib/location";
import { useAttendanceToday, useMyStores } from "@/api/staffHooks";
import { useComplianceKpis } from "@/api/complianceHooks";
import { useAuth } from "@/auth/AuthProvider";
import { Badge, Card, ErrorNote, ListSkeleton, Screen, SectionTitle } from "@/components/ui";
import { fmtDate, niceName } from "@/lib/format";
import { useScanQueue } from "@/lib/useScanQueue";
import { colors, font, radius, shadow } from "@/theme";

const time = (iso: string) => new Date(iso).toLocaleTimeString("en-IN", { hour: "numeric", minute: "2-digit" });
const hm = (min: number) => `${Math.floor(min / 60)}h ${String(min % 60).padStart(2, "0")}m`;

type IconName = React.ComponentProps<typeof Ionicons>["name"];

/** The main job of the day: a full-width button, so the most common action is the easiest to hit. */
function PrimaryAction({ icon, label, sub, badge, onPress }: { icon: IconName; label: string; sub: string; badge?: string; onPress: () => void }) {
  return (
    <Pressable
      onPress={onPress}
      accessibilityRole="button"
      accessibilityLabel={`${label}. ${badge ? `${badge}. ` : ""}${sub}`}
      android_ripple={{ color: "rgba(255,255,255,0.18)" }}
      style={({ pressed }) => ({ minHeight: 84, flexDirection: "row", alignItems: "center", gap: 14, padding: 16, borderRadius: radius.lg, backgroundColor: colors.brand600, opacity: pressed ? 0.92 : 1, ...shadow.card })}
    >
      <View style={{ width: 52, height: 52, borderRadius: radius.md, backgroundColor: "rgba(255,255,255,0.18)", alignItems: "center", justifyContent: "center" }}>
        <Ionicons name={icon} size={26} color={colors.white} />
      </View>
      <View style={{ flex: 1, gap: 3 }}>
        <Text style={{ fontSize: 17, fontWeight: "800", color: colors.white }}>{label}</Text>
        <Text numberOfLines={2} style={{ fontSize: 13, color: "rgba(255,255,255,0.82)" }}>{sub}</Text>
      </View>
      {badge ? (
        <View style={{ paddingHorizontal: 10, paddingVertical: 4, borderRadius: radius.pill, backgroundColor: colors.white }}>
          <Text style={{ fontSize: 12, fontWeight: "800", color: colors.brand700 }}>{badge}</Text>
        </View>
      ) : null}
      <Ionicons name="chevron-forward" size={20} color="rgba(255,255,255,0.85)" />
    </Pressable>
  );
}

/**
 * A module tile: icon, name, one live line and an arrow that says "opens". Two to a row; a tile left on its own
 * stretches across the row. At least 112 points tall, so it is easy to hit.
 */
function Action({ icon, label, sub, badge, onPress, tone }: { icon: IconName; label: string; sub?: string; badge?: string; onPress: () => void; tone: [string, string] }) {
  return (
    <Pressable
      onPress={onPress}
      accessibilityRole="button"
      accessibilityLabel={`${label}. ${badge ? `${badge}. ` : ""}${sub ?? ""}`}
      android_ripple={{ color: colors.brand100 }}
      style={({ pressed }) => ({ flexGrow: 1, flexBasis: "45%", minHeight: 118, backgroundColor: pressed ? colors.surfaceSubtle : colors.surface, borderRadius: radius.lg, borderWidth: 1, borderColor: colors.border, padding: 14, gap: 12, ...shadow.card })}
    >
      <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between" }}>
        <View style={{ width: 44, height: 44, borderRadius: radius.md, backgroundColor: tone[0], alignItems: "center", justifyContent: "center" }}>
          <Ionicons name={icon} size={22} color={tone[1]} />
        </View>
        {badge ? (
          <View style={{ paddingHorizontal: 9, paddingVertical: 3, borderRadius: radius.pill, backgroundColor: colors.warningSoft }}>
            <Text style={{ fontSize: 11, fontWeight: "800", color: colors.warning }}>{badge}</Text>
          </View>
        ) : (
          <Ionicons name="arrow-forward" size={18} color={colors.textFaint} />
        )}
      </View>
      <View style={{ gap: 2 }}>
        <Text style={{ fontSize: 15, fontWeight: "800", color: colors.text }}>{label}</Text>
        {sub ? <Text numberOfLines={2} style={font.small}>{sub}</Text> : null}
      </View>
    </Pressable>
  );
}

export default function Today() {
  const { staff, hasPermission } = useAuth();
  const router = useRouter();
  const qc = useQueryClient();
  const q = useAttendanceToday();
  const queue = useScanQueue();
  const canCompliance = hasPermission("compliance.upload") || hasPermission("compliance.manage");
  // Live lines on the tiles. An admin works with every store, so only an employee gets the "stores left today" count.
  const stores = useMyStores(hasPermission("orders.mark") && !staff?.is_admin);
  const left = stores.data ? stores.data.filter((s) => s.status === "LIVE" && s.today_count === null).length : null;
  const kpis = useComplianceKpis(canCompliance).data;
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
      let reading: Reading = {};
      for (;;) {
        const got = await readLocation();
        if ("reading" in got) { reading = got.reading; break; }
        const why = describeFailure(got.skipped);
        const choice = await new Promise<"retry" | "anyway" | "settings" | "cancel">((resolve) =>
          Alert.alert(
            why.title,
            `${why.text}

You can still check ${kind}; it will be recorded as "location not shared".`,
            [
              { text: "Try again", onPress: () => resolve("retry") },
              ...(why.settings ? [{ text: "Open settings", onPress: () => resolve("settings") }] : []),
              { text: `Check ${kind} anyway`, onPress: () => resolve("anyway") },
            ],
            { cancelable: true, onDismiss: () => resolve("cancel") },
          ),
        );
        if (choice === "retry") continue;
        if (choice === "settings") { void Linking.openSettings(); return; }
        if (choice === "cancel") return;
        break;   // "anyway"
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
                <Text numberOfLines={2} style={{ fontWeight: "700", color: a.check_in_location?.status === "office" ? colors.success : colors.warning, marginTop: 2 }}>{a.check_in_location?.status === "office" ? (a.check_in_location.label ?? "Office") : a.checked_in ? (a.check_in_location?.status === "unknown" ? "Location not shared" : "Away (not from office)") : "–"}</Text>
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

      <SectionTitle>What do you want to do?</SectionTitle>
      {hasPermission("orders.mark") && (
        <PrimaryAction
          icon="create-outline"
          label="Mark orders"
          sub={left === null ? "Enter today's bottle counts" : left === 0 ? "All stores are marked for today" : "Enter today's bottle counts"}
          badge={left === null ? undefined : left === 0 ? "All done" : `${left} left`}
          onPress={() => router.push("/staff/orders")}
        />
      )}
      <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 12, marginTop: 12 }}>
        {canCompliance && (
          <Action icon="id-card-outline" label="Store cards" sub="Upload a card photo" onPress={() => router.push("/staff/cards")} tone={[colors.successSoft, colors.success]} />
        )}
        {canCompliance && (
          <Action icon="shield-checkmark-outline" label="Compliance" sub={kpis ? `${Math.round(kpis.kpis.compliance_percent)}% complete this month` : "Cards, invoices, payment proofs"} onPress={() => router.push("/staff/compliance")} tone={[colors.brand50, colors.brand700]} />
        )}
        {hasPermission("bottles.scan") && (
          <Action icon="qr-code-outline" label="Scan bottles" sub={queue.pending.length ? "Waiting to send" : "Bottles in and out"} badge={queue.pending.length ? `${queue.pending.length} waiting` : undefined} onPress={() => router.push("/staff/scan")} tone={[colors.successSoft, colors.success]} />
        )}
        {hasPermission("cash.add") && (
          <Action icon="wallet-outline" label="Add expense" sub="Record a cash purchase" onPress={() => router.push("/staff/expense/new")} tone={[colors.warningSoft, colors.warning]} />
        )}
        <Action icon="calendar-outline" label="Leave" sub="Apply or check your leave" onPress={() => router.push("/staff/leave")} tone={[colors.dangerSoft, colors.danger]} />
      </View>
    </Screen>
  );
}
