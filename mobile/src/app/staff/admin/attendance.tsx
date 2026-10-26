import { useMemo, useState } from "react";
import { Alert, FlatList, Pressable, Text, TextInput, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useAttendanceDay, useAttendanceMonth, useMarkDays } from "@/api/adminHooks";
import { useAuth } from "@/auth/AuthProvider";
import type { AttendanceDayRow, AttendanceMonth, AttendanceMonthRow, AttendanceStatus } from "@/api/admin";
import { Badge, Button, Chips, Empty, ErrorNote, ListSkeleton } from "@/components/ui";
import { fmtMonth, isoDate } from "@/lib/format";
import { colors, font, radius } from "@/theme";

type Mode = "today" | "month";

const STATUS: Record<AttendanceStatus, { label: string; tone: "success" | "warning" | "danger" | "info" | "neutral" }> = {
  CHECKED_IN: { label: "In now", tone: "success" }, CHECKED_OUT: { label: "Done for the day", tone: "info" }, NO_CHECKOUT: { label: "No check-out", tone: "warning" },
  PRESENT: { label: "Present", tone: "success" }, ON_LEAVE: { label: "On leave", tone: "warning" }, OFF: { label: "Day off", tone: "neutral" }, ABSENT: { label: "Absent", tone: "danger" },
};

const time = (iso: string | null) => (iso ? new Date(iso).toLocaleTimeString("en-IN", { hour: "numeric", minute: "2-digit", hour12: true }).toUpperCase() : null);

function shiftMonth(month: string, by: number): string {
  const [y, m] = month.split("-").map(Number);
  const d = new Date(y, m - 1 + by, 1);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

function Search({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  return (
    <View style={{ flexDirection: "row", alignItems: "center", gap: 8, height: 48, borderRadius: radius.md, backgroundColor: colors.surface, borderWidth: 1.5, borderColor: colors.border, paddingHorizontal: 12 }}>
      <Ionicons name="search" size={18} color={colors.textFaint} />
      <TextInput value={value} onChangeText={onChange} placeholder="Search name, ID or platform" placeholderTextColor={colors.textFaint} accessibilityLabel="Search" style={{ flex: 1, fontSize: 16, color: colors.text }} />
    </View>
  );
}

function DayRow({ r }: { r: AttendanceDayRow }) {
  const st = STATUS[r.status];
  const inAt = time(r.check_in_at);
  const outAt = time(r.check_out_at);
  return (
    <View style={{ backgroundColor: colors.surface, borderRadius: radius.lg, borderWidth: 1, borderColor: colors.border, padding: 14, gap: 4 }}>
      <View style={{ flexDirection: "row", alignItems: "flex-start", justifyContent: "space-between", gap: 10 }}>
        <Text style={{ flex: 1, fontSize: 15, fontWeight: "700", color: colors.text }}>{r.full_name}</Text>
        <Badge tone={st.tone}>{st.label}</Badge>
      </View>
      <Text numberOfLines={1} style={font.small}>{r.employee_code}{r.platform ? ` · ${r.platform}` : ""}{r.region ? ` · ${r.region}` : ""}</Text>
      {inAt && <Text style={font.small}>In {inAt}{outAt ? ` · Out ${outAt}` : ""}{r.late ? " · late" : ""}{r.location.label && r.location.label !== "—" ? ` · ${r.location.label}` : ""}</Text>}
      {r.status === "ON_LEAVE" && r.leave_type && <Text style={font.small}>{r.leave_type}</Text>}
    </View>
  );
}

function DatesGrid({ month, r }: { month: AttendanceMonth; r: AttendanceMonthRow }) {
  const { hasPermission } = useAuth();
  const canMark = hasPermission("attendance.edit");                    // the developer: marks days by hand, backlog days included
  const mark = useMarkDays();
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const present = new Set(r.present_dates);
  const leave = new Set(r.leave_dates);
  const first = new Date(`${month.dates[0]}T00:00:00`).getDay();
  const fail = (e: Error) => Alert.alert("Couldn't save", e.message);
  function markPicked() {
    const dates = [...picked].sort();
    Alert.alert("Mark present?", `${r.full_name} will count as present on ${dates.length} day${dates.length === 1 ? "" : "s"}. No times are recorded.`, [
      { text: "Cancel", style: "cancel" },
      { text: "Mark present", onPress: () => mark.mutate({ userId: r.user_id, dates, present: true }, { onSuccess: () => setPicked(new Set()), onError: fail }) },
    ]);
  }
  function removeOne(iso: string) {
    Alert.alert("Remove this mark?", `${r.full_name}, ${iso}. A day they really checked in on stays as it is.`, [
      { text: "Cancel", style: "cancel" },
      { text: "Remove", style: "destructive", onPress: () => mark.mutate({ userId: r.user_id, dates: [iso], present: false }, {
        onSuccess: (res) => { if (res.removed === 0) Alert.alert("Not removed", "This day is a real check-in, so it was left as it is."); }, onError: fail }) },
    ]);
  }
  return (
    <View style={{ marginTop: 10 }}>
      <View style={{ flexDirection: "row", flexWrap: "wrap" }}>
        {["S", "M", "T", "W", "T", "F", "S"].map((w, i) => <Text key={i} style={{ width: "14.285%", textAlign: "center", fontSize: 11, color: colors.textFaint, fontWeight: "700", marginBottom: 4 }}>{w}</Text>)}
        {Array.from({ length: first }).map((_, i) => <View key={`b${i}`} style={{ width: "14.285%" }} />)}
        {month.dates.map((iso) => {
          const d = new Date(`${iso}T00:00:00`);
          const off = d.getDay() === (month.weekly_off_weekday + 1) % 7 || Boolean(month.holidays?.[iso]);          // Python Monday=0 -> JS Sunday=0; a company holiday is a day off too
          const future = iso > month.today;
          const kind = present.has(iso) ? "present" : leave.has(iso) ? "leave" : off ? "off" : future ? "future" : "absent";
          const [bg, fg] = kind === "present" ? [colors.successSoft, colors.success] : kind === "leave" ? [colors.warningSoft, colors.warning] : kind === "absent" ? [colors.dangerSoft, colors.danger] : [colors.surfaceMuted, colors.textFaint];
          const editable = canMark && !future;
          const on = picked.has(iso);
          return (
            <View key={iso} style={{ width: "14.285%", padding: 2 }}>
              <Pressable
                disabled={!editable}
                onPress={() => (present.has(iso) ? removeOne(iso) : setPicked((s) => { const n = new Set(s); if (n.has(iso)) n.delete(iso); else n.add(iso); return n; }))}
                accessibilityRole={editable ? "button" : undefined} accessibilityLabel={`${iso}: ${kind}${on ? ", selected" : ""}`}
                style={{ height: 34, borderRadius: 8, backgroundColor: bg, alignItems: "center", justifyContent: "center", borderWidth: on ? 2 : 0, borderColor: colors.brand600 }}>
                <Text style={{ color: fg, fontWeight: kind === "present" ? "800" : "600", fontSize: 13 }}>{d.getDate()}</Text>
              </Pressable>
            </View>
          );
        })}
      </View>
      <Text style={[font.tiny, { marginTop: 8 }]}>Green present · Amber on leave · Red absent · Grey day off / not yet</Text>
      {canMark && (
        <View style={{ marginTop: 10, gap: 8 }}>
          <Text style={font.small}>{picked.size ? `${picked.size} day${picked.size === 1 ? "" : "s"} selected` : "Tap days to select them, then mark them present. Tap a green day to take a hand-made mark away."}</Text>
          {picked.size > 0 && (
            <View style={{ flexDirection: "row", gap: 8 }}>
              <View style={{ flex: 1 }}><Button title={`Mark ${picked.size} present`} loading={mark.isPending} onPress={markPicked} /></View>
              <Button title="Clear" variant="ghost" onPress={() => setPicked(new Set())} />
            </View>
          )}
        </View>
      )}
    </View>
  );
}

function MonthCard({ month, r }: { month: AttendanceMonth; r: AttendanceMonthRow }) {
  const [open, setOpen] = useState(false);
  return (
    <Pressable onPress={() => setOpen((o) => !o)} accessibilityRole="button" accessibilityState={{ expanded: open }} accessibilityLabel={`${r.full_name}, ${r.days_present} days present`}
      style={{ backgroundColor: colors.surface, borderRadius: radius.lg, borderWidth: 1, borderColor: colors.border, padding: 14 }}>
      <View style={{ flexDirection: "row", alignItems: "center", gap: 10 }}>
        <View style={{ flex: 1 }}>
          <Text style={{ fontSize: 15, fontWeight: "700", color: colors.text }}>{r.full_name}</Text>
          <Text numberOfLines={1} style={font.small}>{r.employee_code}{r.platform ? ` · ${r.platform}` : ""}</Text>
        </View>
        <View style={{ alignItems: "flex-end" }}>
          <Text style={{ fontSize: 20, fontWeight: "800", color: colors.text }}>{r.days_present}</Text>
          <Text style={font.tiny}>days present</Text>
        </View>
        <Ionicons name={open ? "chevron-up" : "chevron-down"} size={18} color={colors.textFaint} />
      </View>
      <Text style={[font.small, { marginTop: 4 }]}>{r.leave_days ? `${r.leave_days} on leave · ` : ""}{r.absent_days} absent{r.late_days ? ` · ${r.late_days} late` : ""}</Text>
      {open && <DatesGrid month={month} r={r} />}
    </Pressable>
  );
}

/** Attendance for admins: who is in today, and per employee the dates they were present in any month. */
export default function AdminAttendance() {
  const [mode, setMode] = useState<Mode>("today");
  const [month, setMonth] = useState(() => isoDate(new Date()).slice(0, 7));
  const [needle, setNeedle] = useState("");
  const day = useAttendanceDay(mode === "today");
  const mon = useAttendanceMonth(month, mode === "month");
  const q = mode === "today" ? day : mon;
  const n = needle.trim().toLowerCase();
  const match = (r: { full_name: string; employee_code: string; platform: string | null }) => !n || `${r.full_name} ${r.employee_code} ${r.platform ?? ""}`.toLowerCase().includes(n);
  const dayRows = useMemo(() => (day.data?.rows ?? []).filter(match), [day.data, n]); // eslint-disable-line react-hooks/exhaustive-deps
  const monthRows = useMemo(() => (mon.data?.rows ?? []).filter(match), [mon.data, n]); // eslint-disable-line react-hooks/exhaustive-deps
  const thisMonth = isoDate(new Date()).slice(0, 7);
  const s = day.data?.summary;

  const header = (
    <View style={{ gap: 12, marginBottom: 4 }}>
      <Chips<Mode> options={[{ label: "Today", value: "today" }, { label: "Monthly dates", value: "month" }]} value={mode} onChange={setMode} />
      {mode === "today" && s && (
        <View style={{ backgroundColor: colors.ink950, borderRadius: radius.xl, padding: 16 }}>
          <Text style={{ color: "rgba(255,255,255,0.65)", fontSize: 12 }}>{day.data?.holiday ? `Holiday today: ${day.data.holiday}` : day.data?.is_weekly_off ? "Weekly off today" : "Present today"}</Text>
          <Text style={{ color: colors.white, fontSize: 30, fontWeight: "800" }}>{s.present} <Text style={{ fontSize: 15, color: "rgba(255,255,255,0.6)", fontWeight: "600" }}>of {s.expected}</Text></Text>
          <Text style={{ color: "rgba(255,255,255,0.7)", fontSize: 13, marginTop: 4 }}>{s.checked_in_now} in now · {s.late} late · {s.on_leave} on leave · {s.absent} absent</Text>
        </View>
      )}
      {mode === "month" && (
        <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between", backgroundColor: colors.surface, borderRadius: radius.lg, borderWidth: 1, borderColor: colors.border, paddingHorizontal: 8, height: 52 }}>
          <Pressable onPress={() => setMonth(shiftMonth(month, -1))} accessibilityRole="button" accessibilityLabel="Previous month" hitSlop={10} style={{ padding: 8 }}><Ionicons name="chevron-back" size={20} color={colors.text} /></Pressable>
          <Text style={{ fontSize: 16, fontWeight: "800", color: colors.text }}>{fmtMonth(`${month}-01`)}</Text>
          <Pressable disabled={month >= thisMonth} onPress={() => setMonth(shiftMonth(month, 1))} accessibilityRole="button" accessibilityLabel="Next month" hitSlop={10} style={{ padding: 8, opacity: month >= thisMonth ? 0.3 : 1 }}><Ionicons name="chevron-forward" size={20} color={colors.text} /></Pressable>
        </View>
      )}
      <Search value={needle} onChange={setNeedle} />
    </View>
  );

  const empty = q.isLoading ? <ListSkeleton /> : q.isError ? <ErrorNote message={q.error.message} onRetry={() => q.refetch()} /> : <Empty title="Nobody matches" text="Try another name." />;

  return (
    <View style={{ flex: 1, backgroundColor: colors.surfaceSubtle }}>
      {mode === "today" ? (
        <FlatList data={dayRows} keyExtractor={(r) => r.user_id} keyboardShouldPersistTaps="handled" onRefresh={() => day.refetch()} refreshing={day.isRefetching && !day.isLoading}
          contentContainerStyle={{ padding: 16, paddingBottom: 40, gap: 10 }} ListHeaderComponent={header} ListEmptyComponent={empty} renderItem={({ item }) => <DayRow r={item} />} />
      ) : (
        <FlatList data={monthRows} keyExtractor={(r) => r.user_id} keyboardShouldPersistTaps="handled" onRefresh={() => mon.refetch()} refreshing={mon.isRefetching && !mon.isLoading}
          contentContainerStyle={{ padding: 16, paddingBottom: 40, gap: 10 }} ListHeaderComponent={header} ListEmptyComponent={empty}
          renderItem={({ item }) => (mon.data ? <MonthCard month={mon.data} r={item} /> : null)} />
      )}
    </View>
  );
}
