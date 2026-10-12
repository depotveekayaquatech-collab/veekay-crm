import { Alert, Text, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import { staffApi, type LeaveItem } from "@/api/staff";
import { useLeaves, useStaffWrite } from "@/api/staffHooks";
import { Badge, Button, Card, Empty, ErrorNote, ListSkeleton, Screen, SectionTitle } from "@/components/ui";
import { fmtDate, titleCase } from "@/lib/format";
import { colors, font } from "@/theme";

const TONE = { PENDING: "warning", APPROVED: "success", REJECTED: "danger", CANCELLED: "neutral" } as const;
const TYPES = ["CASUAL", "SICK", "PAID", "UNPAID"] as const;

export default function Leave() {
  const router = useRouter();
  const q = useLeaves();
  const cancel = useStaffWrite((id: string) => staffApi.cancelLeave(id), ["s-leaves", "s-attendance"]);

  function confirmCancel(l: LeaveItem) {
    Alert.alert("Cancel this request?", `${titleCase(l.leave_type)} leave, ${fmtDate(l.start_date)}${l.end_date !== l.start_date ? ` to ${fmtDate(l.end_date)}` : ""}.`, [
      { text: "Keep it", style: "cancel" },
      { text: "Cancel request", style: "destructive", onPress: () => cancel.mutate(l.id, { onError: (e) => Alert.alert("Couldn't cancel", e.message) }) },
    ]);
  }

  return (
    <Screen onRefresh={() => q.refetch()} refreshing={q.isRefetching && !q.isLoading}>
      <Button title="Apply for leave" onPress={() => router.push("/staff/leave/new")} icon={<Ionicons name="calendar-outline" size={20} color="#fff" />} />

      {q.isLoading ? <View style={{ marginTop: 16 }}><ListSkeleton /></View> : q.isError ? <View style={{ marginTop: 16 }}><ErrorNote message={q.error.message} onRetry={() => q.refetch()} /></View> : (
        <>
          <SectionTitle>Taken in {q.data!.year}</SectionTitle>
          <View style={{ flexDirection: "row", gap: 10 }}>
            {TYPES.map((t) => (
              <Card key={t} style={{ flex: 1, padding: 12, alignItems: "center" }}>
                <Text style={{ fontSize: 22, fontWeight: "800", color: colors.text }}>{q.data!.taken[t] ?? 0}</Text>
                <Text style={font.tiny}>{titleCase(t)}</Text>
              </Card>
            ))}
          </View>
          {q.data!.pending > 0 && <Text style={[font.small, { marginTop: 10 }]}>{q.data!.pending} request{q.data!.pending === 1 ? " is" : "s are"} waiting for approval.</Text>}

          <SectionTitle>Your requests</SectionTitle>
          {q.data!.items.length === 0 ? <Empty title="No leave requests" text="Apply above and your manager is notified." /> : (
            <View style={{ gap: 10 }}>
              {q.data!.items.map((l) => (
                <Card key={l.id}>
                  <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: 10 }}>
                    <Text style={{ fontSize: 15, fontWeight: "700", color: colors.text }}>{titleCase(l.leave_type)} · {l.days} day{l.days === 1 ? "" : "s"}{l.half_day ? " (half)" : ""}</Text>
                    <Badge tone={TONE[l.status]}>{titleCase(l.status)}</Badge>
                  </View>
                  <Text style={[font.small, { marginTop: 4 }]}>{fmtDate(l.start_date)}{l.end_date !== l.start_date ? ` to ${fmtDate(l.end_date)}` : ""}</Text>
                  <Text style={{ marginTop: 6, color: colors.text, lineHeight: 20 }}>{l.reason}</Text>
                  {l.review_note ? <Text style={[font.small, { marginTop: 6 }]}>{l.reviewed_by_name ?? "Reviewer"}: {l.review_note}</Text> : null}
                  {l.can_cancel ? <Text onPress={() => confirmCancel(l)} accessibilityRole="button" style={{ marginTop: 10, color: colors.danger, fontWeight: "700" }}>Cancel request</Text> : null}
                </Card>
              ))}
            </View>
          )}
        </>
      )}
    </Screen>
  );
}
