import { useState } from "react";
import { Alert, Pressable, Switch, Text, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import { staffApi, type LeaveType } from "@/api/staff";
import { useStaffWrite } from "@/api/staffHooks";
import { Button, Card, Chips, ErrorNote, Field, Screen } from "@/components/ui";
import { MonthGrid, type CellState } from "@/components/MonthGrid";
import { daysAgo, fmtDate } from "@/lib/format";
import { colors, font } from "@/theme";

const TYPES: { label: string; value: LeaveType }[] = [
  { label: "Casual", value: "CASUAL" }, { label: "Sick", value: "SICK" }, { label: "Paid", value: "PAID" }, { label: "Unpaid", value: "UNPAID" },
];

export default function ApplyLeave() {
  const router = useRouter();
  const now = new Date();
  const [ym, setYm] = useState({ y: now.getFullYear(), m: now.getMonth() + 1 });
  const [type, setType] = useState<LeaveType>("CASUAL");
  const [start, setStart] = useState<string | null>(null);
  const [end, setEnd] = useState<string | null>(null);
  const [half, setHalf] = useState(false);
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const apply = useStaffWrite((b: Parameters<typeof staffApi.applyLeave>[0]) => staffApi.applyLeave(b), ["s-leaves", "s-attendance"]);
  const today = daysAgo(0);

  // First tap starts the range, second tap ends it (like booking apps); tapping before the start restarts it.
  function pick(iso: string) {
    if (!start || (start && end && start !== end) || iso < start) { setStart(iso); setEnd(iso); return; }
    setEnd(iso);
  }
  const single = !!start && start === end;
  const days = start && end ? Math.round((new Date(end).getTime() - new Date(start).getTime()) / 86_400_000) + 1 : 0;

  const state = (iso: string): CellState => ({
    disabled: iso < today,
    today: iso === today,
    selected: iso === start || iso === end,
    inRange: !!start && !!end && iso > start && iso < end,
  });

  function shift(d: number) {
    setYm(({ y, m }) => { const n = new Date(y, m - 1 + d, 1); return { y: n.getFullYear(), m: n.getMonth() + 1 }; });
  }

  function submit() {
    if (!start || !end) return;
    setError(null);
    apply.mutate({ leave_type: type, start_date: start, end_date: end, half_day: single && half, reason: reason.trim() }, {
      onSuccess: () => { Alert.alert("Request sent", "Your manager will review it."); router.back(); },
      onError: (e) => setError(e.message),
    });
  }

  return (
    <Screen keyboard>
      <View style={{ gap: 18 }}>
        <View style={{ gap: 8 }}>
          <Text style={{ fontSize: 13, fontWeight: "600", color: colors.text }}>Type of leave</Text>
          <Chips options={TYPES} value={type} onChange={setType} />
        </View>

        <Card style={{ padding: 10 }}>
          <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: 6, paddingBottom: 4 }}>
            <Pressable onPress={() => shift(-1)} accessibilityRole="button" accessibilityLabel="Previous month" hitSlop={10}><Ionicons name="chevron-back" size={22} color={colors.text} /></Pressable>
            <Text style={font.h2}>{new Date(ym.y, ym.m - 1, 1).toLocaleDateString("en-IN", { month: "long", year: "numeric" })}</Text>
            <Pressable onPress={() => shift(1)} accessibilityRole="button" accessibilityLabel="Next month" hitSlop={10}><Ionicons name="chevron-forward" size={22} color={colors.text} /></Pressable>
          </View>
          <MonthGrid year={ym.y} month={ym.m} state={state} onPress={pick} />
        </Card>

        <View style={{ padding: 14, borderRadius: 12, backgroundColor: colors.brand50 }}>
          <Text style={{ color: colors.brand800, fontWeight: "700" }}>
            {start && end ? (single ? fmtDate(start) : `${fmtDate(start)} to ${fmtDate(end)}`) : "Tap a start date, then an end date"}
          </Text>
          {days > 0 && <Text style={{ color: colors.brand800, marginTop: 2 }}>{single && half ? "Half day" : `${days} day${days === 1 ? "" : "s"}`}</Text>}
        </View>

        {single && (
          <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between" }}>
            <Text style={{ fontWeight: "600", color: colors.text }}>Half day</Text>
            <Switch value={half} onValueChange={setHalf} trackColor={{ true: colors.brand500 }} />
          </View>
        )}

        <Field label="Reason" value={reason} onChangeText={setReason} multiline maxLength={500} placeholder="Why do you need the leave?" />
        {error ? <ErrorNote message={error} /> : null}
        <Button title="Send request" onPress={submit} loading={apply.isPending} disabled={!start || !end || !reason.trim()} />
      </View>
    </Screen>
  );
}
