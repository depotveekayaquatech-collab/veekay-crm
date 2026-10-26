import { Pressable, Text, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useAttendanceDay, useBottleSummary, useDueBills, useInsights, useLeavesAll, usePending } from "@/api/adminHooks";
import { useAuth } from "@/auth/AuthProvider";
import { Card, ErrorNote, ListSkeleton, Screen, SectionTitle } from "@/components/ui";
import { SyncCard } from "@/components/SyncCard";
import { fmtNumber } from "@/lib/format";
import { colors, font, radius } from "@/theme";

type IconName = React.ComponentProps<typeof Ionicons>["name"];

function Alert({ icon, tone, title, sub, onPress }: { icon: IconName; tone: "bad" | "warn"; title: string; sub: string; onPress: () => void }) {
  const [bg, fg] = tone === "bad" ? [colors.dangerSoft, colors.danger] : [colors.warningSoft, colors.warning];
  return (
    <Pressable onPress={onPress} accessibilityRole="button" accessibilityLabel={`${title}. ${sub}`} android_ripple={{ color: colors.brand100 }}
      style={{ flexDirection: "row", alignItems: "center", gap: 12, padding: 14, borderRadius: radius.lg, backgroundColor: bg }}>
      <Ionicons name={icon} size={22} color={fg} />
      <View style={{ flex: 1 }}>
        <Text style={{ fontSize: 15, fontWeight: "800", color: fg }}>{title}</Text>
        <Text style={{ fontSize: 13, color: fg, opacity: 0.85 }}>{sub}</Text>
      </View>
      <Ionicons name="chevron-forward" size={18} color={fg} />
    </Pressable>
  );
}

export default function AdminOverview() {
  const { hasPermission } = useAuth();
  const router = useRouter();
  const qc = useQueryClient();
  const [refreshing, setRefreshing] = useState(false);
  const canOrders = hasPermission("orders.overview");
  const canLeave = hasPermission("leave.review");
  const canBottles = hasPermission("bottles.view");
  const canBills = hasPermission("accounts.view");
  const canAttendance = hasPermission("attendance.view");

  const ins = useInsights(canOrders);
  const pending = usePending(0, canOrders);
  const leaves = useLeavesAll("PENDING", canLeave);
  const bottles = useBottleSummary(canBottles);
  const bills = useDueBills(canBills);
  const attendance = useAttendanceDay(canAttendance);

  const i = ins.data;
  const delta = i && i.bottles_yesterday ? Math.round(((i.bottles_today - i.bottles_yesterday) / i.bottles_yesterday) * 100) : null;
  const max = Math.max(1, ...(i?.trend.map((t) => t.bottles) ?? [1]));

  async function refresh() {
    setRefreshing(true);
    await qc.invalidateQueries();
    setRefreshing(false);
  }

  const alerts = [
    pending.data && pending.data.pending > 0 ? { key: "p", icon: "alert-circle-outline" as const, tone: "warn" as const, title: `${pending.data.pending} stores not marked today`, sub: `${pending.data.marked} of ${pending.data.live_stores} live stores done`, to: "/staff/admin/pending" } : null,
    leaves.data && leaves.data.pending > 0 ? { key: "l", icon: "calendar-outline" as const, tone: "warn" as const, title: `${leaves.data.pending} leave request${leaves.data.pending === 1 ? "" : "s"} waiting`, sub: "Approve or reject", to: "/staff/admin/leaves" } : null,
    bottles.data && bottles.data.overdue > 0 ? { key: "b", icon: "cube-outline" as const, tone: "bad" as const, title: `${bottles.data.overdue} bottle${bottles.data.overdue === 1 ? "" : "s"} overdue`, sub: `At a store for more than ${bottles.data.lost_after_days} days`, to: "/staff/admin/bottles" } : null,
    bills.data && bills.data.total > 0 ? { key: "r", icon: "receipt-outline" as const, tone: "bad" as const, title: `${bills.data.total} bill${bills.data.total === 1 ? "" : "s"} past due`, sub: "Most overdue first", to: "/staff/admin/bills" } : null,
  ].filter((a): a is NonNullable<typeof a> => a !== null);

  return (
    <Screen onRefresh={refresh} refreshing={refreshing}>
      {canOrders && (
        <>
          <SectionTitle>Today</SectionTitle>
          {ins.isLoading ? <ListSkeleton rows={2} /> : ins.isError ? <ErrorNote message={ins.error.message} onRetry={() => ins.refetch()} /> : i ? (
            <>
              <View style={{ backgroundColor: colors.ink950, borderRadius: radius.xl, padding: 18 }}>
                <Text style={{ color: "rgba(255,255,255,0.65)", fontSize: 12 }}>Bottles delivered today</Text>
                <View style={{ flexDirection: "row", alignItems: "flex-end", justifyContent: "space-between", marginTop: 2 }}>
                  <Text style={{ color: colors.white, fontSize: 36, fontWeight: "800", letterSpacing: -1 }}>{fmtNumber(i.bottles_today)}</Text>
                  {delta !== null && (
                    <View style={{ backgroundColor: "rgba(255,255,255,0.12)", borderRadius: radius.pill, paddingHorizontal: 10, paddingVertical: 4 }}>
                      <Text style={{ color: delta >= 0 ? "#7be0a8" : "#ffa3a3", fontWeight: "800", fontSize: 12 }}>{delta >= 0 ? "▲" : "▼"} {Math.abs(delta)}% vs yesterday</Text>
                    </View>
                  )}
                </View>
                <Text style={{ color: "rgba(255,255,255,0.55)", fontSize: 12, marginTop: 2 }}>{i.entries_today} store entries · yesterday {fmtNumber(i.bottles_yesterday)}</Text>
                <View style={{ flexDirection: "row", alignItems: "flex-end", gap: 6, height: 64, marginTop: 14 }}>
                  {i.trend.map((t, k) => (
                    <View key={t.date} style={{ flex: 1, alignItems: "center", gap: 3, justifyContent: "flex-end", height: "100%" }}>
                      <View style={{ width: "100%", borderRadius: 3, minHeight: 3, height: `${Math.max(5, (t.bottles / max) * 100)}%`, backgroundColor: k === i.trend.length - 1 ? colors.aqua500 : colors.brand500 }} />
                    </View>
                  ))}
                </View>
              </View>

              <SectionTitle>Platforms today</SectionTitle>
              <Card style={{ gap: 14 }}>
                {i.platforms.map((p) => (
                  <View key={p.slug}>
                    <View style={{ flexDirection: "row", justifyContent: "space-between" }}>
                      <Text style={{ fontWeight: "700", color: colors.text }}>{p.label}</Text>
                      <Text style={font.small}>{p.entries_done} / {p.total_stores} stores · {fmtNumber(p.bottles)} bottles</Text>
                    </View>
                    <View style={{ height: 8, borderRadius: 4, backgroundColor: colors.surfaceMuted, marginTop: 6, overflow: "hidden" }}>
                      <View style={{ height: 8, borderRadius: 4, backgroundColor: colors.brand500, width: `${Math.min(100, p.percent)}%` }} />
                    </View>
                  </View>
                ))}
              </Card>
            </>
          ) : null}
        </>
      )}

      {canAttendance && (
        <>
          <SectionTitle>Attendance today</SectionTitle>
          {attendance.isLoading ? <ListSkeleton rows={1} /> : attendance.isError ? <ErrorNote message={attendance.error.message} onRetry={() => attendance.refetch()} /> : attendance.data ? (
            <Card style={{ gap: 12 }}>
              <View style={{ flexDirection: "row", alignItems: "flex-end", justifyContent: "space-between" }}>
                <Text style={{ fontSize: 30, fontWeight: "800", color: colors.text }}>
                  {attendance.data.summary.present}
                  <Text style={{ fontSize: 15, fontWeight: "600", color: colors.textMuted }}> of {attendance.data.summary.expected} present</Text>
                </Text>
                {attendance.data.is_weekly_off && <Text style={font.small}>Weekly off</Text>}
              </View>
              <View style={{ height: 8, borderRadius: 4, backgroundColor: colors.surfaceMuted, overflow: "hidden" }}>
                <View style={{ height: 8, borderRadius: 4, backgroundColor: colors.success, width: `${attendance.data.summary.expected ? Math.min(100, (attendance.data.summary.present / attendance.data.summary.expected) * 100) : 0}%` }} />
              </View>
              <Text style={font.small}>
                {attendance.data.summary.checked_in_now} in now · {attendance.data.summary.late} late · {attendance.data.summary.on_leave} on leave · {attendance.data.summary.absent} absent
              </Text>
              <Pressable onPress={() => router.push("/staff/admin/attendance" as never)} accessibilityRole="button" accessibilityLabel="See every employee's present dates"
                android_ripple={{ color: colors.brand100 }} style={{ minHeight: 46, borderRadius: radius.md, backgroundColor: colors.brand50, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 8 }}>
                <Ionicons name="calendar-outline" size={18} color={colors.brand600} />
                <Text style={{ color: colors.brand600, fontWeight: "800" }}>Who was present, date by date</Text>
              </Pressable>
            </Card>
          ) : null}
        </>
      )}

      {alerts.length > 0 && (
        <>
          <SectionTitle>Needs attention</SectionTitle>
          <View style={{ gap: 10 }}>
            {alerts.map((a) => <Alert key={a.key} icon={a.icon} tone={a.tone} title={a.title} sub={a.sub} onPress={() => router.push(a.to as never)} />)}
          </View>
        </>
      )}
      {alerts.length === 0 && (ins.data || pending.data) && (
        <View style={{ marginTop: 16, padding: 14, borderRadius: radius.lg, backgroundColor: colors.successSoft, flexDirection: "row", gap: 10, alignItems: "center" }}>
          <Ionicons name="checkmark-circle" size={22} color={colors.success} />
          <Text style={{ color: colors.success, fontWeight: "700", flex: 1 }}>Nothing needs attention right now.</Text>
        </View>
      )}

      <SectionTitle>Reports</SectionTitle>
      <Card style={{ padding: 0, overflow: "hidden" }}>
        {canOrders && <NavRow icon="clipboard-outline" label="Stores yet to mark" value={pending.data ? String(pending.data.pending) : undefined} onPress={() => router.push("/staff/admin/pending")} />}
        {canOrders && <NavRow icon="speedometer-outline" label="Employee performance" onPress={() => router.push("/staff/admin/performance" as never)} />}
        {canAttendance && <NavRow icon="people-outline" label="Attendance by employee" value={attendance.data ? `${attendance.data.summary.present}/${attendance.data.summary.expected}` : undefined} onPress={() => router.push("/staff/admin/attendance" as never)} />}
        {canLeave && <NavRow icon="calendar-outline" label="Leave approvals" value={leaves.data ? String(leaves.data.pending) : undefined} onPress={() => router.push("/staff/admin/leaves")} />}
        {canBottles && <NavRow icon="cube-outline" label="Overdue bottles" value={bottles.data ? String(bottles.data.overdue) : undefined} onPress={() => router.push("/staff/admin/bottles")} />}
        {canBills && <NavRow icon="receipt-outline" label="Bills past due" value={bills.data ? String(bills.data.total) : undefined} onPress={() => router.push("/staff/admin/bills")} />}
      </Card>

      <SyncCard />
    </Screen>
  );
}

function NavRow({ icon, label, value, onPress }: { icon: IconName; label: string; value?: string; onPress: () => void }) {
  return (
    <Pressable onPress={onPress} accessibilityRole="button" android_ripple={{ color: colors.brand100 }} style={{ minHeight: 54, paddingHorizontal: 16, flexDirection: "row", alignItems: "center", gap: 12, borderTopWidth: 1, borderTopColor: colors.border }}>
      <Ionicons name={icon} size={20} color={colors.brand600} />
      <Text style={{ flex: 1, fontSize: 15, fontWeight: "600", color: colors.text }}>{label}</Text>
      {value !== undefined && <Text style={{ fontWeight: "800", color: colors.text }}>{value}</Text>}
      <Ionicons name="chevron-forward" size={18} color={colors.textFaint} />
    </Pressable>
  );
}
