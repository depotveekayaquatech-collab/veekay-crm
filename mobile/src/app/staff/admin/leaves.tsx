import { useState } from "react";
import { Alert, Modal, Text, View } from "react-native";
import { useReviewLeave, useLeavesAll } from "@/api/adminHooks";
import type { LeaveAdminItem } from "@/api/admin";
import { Badge, Button, Card, Chips, Empty, ErrorNote, Field, ListSkeleton, Screen } from "@/components/ui";
import { fmtDate, titleCase } from "@/lib/format";
import { colors, font, radius } from "@/theme";

const TONE = { PENDING: "warning", APPROVED: "success", REJECTED: "danger", CANCELLED: "neutral" } as const;
type Filter = "PENDING" | "ALL";

export default function LeaveApprovals() {
  const [filter, setFilter] = useState<Filter>("PENDING");
  const q = useLeavesAll(filter === "ALL" ? "" : "PENDING");
  const review = useReviewLeave();
  const [rejecting, setRejecting] = useState<LeaveAdminItem | null>(null);
  const [note, setNote] = useState("");

  function decide(l: LeaveAdminItem, approve: boolean, why = "") {
    review.mutate({ id: l.id, approve, note: why }, {
      onSuccess: () => { setRejecting(null); setNote(""); },
      onError: (e) => Alert.alert("Couldn't save", e.message),
    });
  }

  function approve(l: LeaveAdminItem) {
    Alert.alert("Approve this leave?", `${l.person?.name ?? "Employee"}: ${fmtDate(l.start_date)}${l.end_date !== l.start_date ? ` to ${fmtDate(l.end_date)}` : ""}.`, [
      { text: "Cancel", style: "cancel" }, { text: "Approve", onPress: () => decide(l, true) },
    ]);
  }

  return (
    <Screen onRefresh={() => q.refetch()} refreshing={q.isRefetching && !q.isLoading}>
      <Chips<Filter> options={[{ label: `Waiting${q.data && filter === "PENDING" ? ` ${q.data.pending}` : ""}`, value: "PENDING" }, { label: "All requests", value: "ALL" }]} value={filter} onChange={setFilter} />
      <View style={{ marginTop: 14, gap: 10 }}>
        {q.isLoading ? <ListSkeleton /> : q.isError ? <ErrorNote message={q.error.message} onRetry={() => q.refetch()} /> : q.data!.items.length === 0 ? (
          <Empty title={filter === "PENDING" ? "No requests waiting" : "No leave requests"} text="New requests from your team appear here." />
        ) : q.data!.items.map((l) => (
          <Card key={l.id}>
            <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: 10 }}>
              <Text style={{ flex: 1, fontSize: 15, fontWeight: "800", color: colors.text }}>{l.person?.name ?? "Employee"}</Text>
              <Badge tone={TONE[l.status]}>{titleCase(l.status)}</Badge>
            </View>
            <Text style={font.small}>{l.person?.code}{l.person?.region ? ` · ${l.person.region}` : ""}</Text>
            <Text style={{ marginTop: 8, fontWeight: "700", color: colors.text }}>{titleCase(l.leave_type)} · {l.days} day{l.days === 1 ? "" : "s"}{l.half_day ? " (half)" : ""}</Text>
            <Text style={font.small}>{fmtDate(l.start_date)}{l.end_date !== l.start_date ? ` to ${fmtDate(l.end_date)}` : ""}</Text>
            <Text style={{ marginTop: 6, color: colors.text, lineHeight: 20 }}>{l.reason}</Text>
            {l.review_note ? <Text style={[font.small, { marginTop: 6 }]}>{l.reviewed_by_name ?? "Reviewer"}: {l.review_note}</Text> : null}
            {l.status === "PENDING" && (
              <View style={{ flexDirection: "row", gap: 10, marginTop: 12 }}>
                <Button title="Reject" variant="secondary" onPress={() => setRejecting(l)} style={{ flex: 1, minHeight: 46 }} />
                <Button title="Approve" onPress={() => approve(l)} loading={review.isPending && review.variables?.id === l.id} style={{ flex: 1, minHeight: 46 }} />
              </View>
            )}
          </Card>
        ))}
      </View>

      <Modal visible={!!rejecting} transparent animationType="fade" onRequestClose={() => setRejecting(null)}>
        <View style={{ flex: 1, backgroundColor: "rgba(0,0,0,0.45)", justifyContent: "center", padding: 24 }}>
          <View style={{ backgroundColor: colors.surface, borderRadius: radius.xl, padding: 18, gap: 14 }}>
            <Text style={{ fontSize: 17, fontWeight: "800", color: colors.text }}>Reject {rejecting?.person?.name ?? "this"} request?</Text>
            <Field label="Note for the employee (optional)" value={note} onChangeText={setNote} multiline maxLength={500} autoFocus />
            <View style={{ flexDirection: "row", gap: 10 }}>
              <Button title="Back" variant="secondary" onPress={() => setRejecting(null)} style={{ flex: 1 }} />
              <Button title="Reject" variant="danger" onPress={() => rejecting && decide(rejecting, false, note.trim())} loading={review.isPending} style={{ flex: 1 }} />
            </View>
          </View>
        </View>
      </Modal>
    </Screen>
  );
}
