import { useState } from "react";
import { Pressable, Text, View } from "react-native";
import { type Payslip, type PayslipDay } from "@/api/staff";
import { usePayslips } from "@/api/staffHooks";
import { Badge, Card, Empty, ErrorNote, ListSkeleton, Screen } from "@/components/ui";
import { fmtDate, fmtMoney, titleCase } from "@/lib/format";
import { colors, font } from "@/theme";

const time = (iso: string | null) => (iso ? new Date(iso).toLocaleTimeString("en-IN", { hour: "numeric", minute: "2-digit" }) : "–");
const hm = (min: number) => `${Math.floor(min / 60)}h ${String(min % 60).padStart(2, "0")}m`;
const dayName = (iso: string) => new Date(`${iso}T12:00:00`).toLocaleDateString("en-IN", { weekday: "short", day: "numeric", month: "short" });
const counts = (n: number) => (n === 1 ? "1 day" : n === 0.5 ? "½ day" : n === 0 ? "–" : `${n} days`);

function what(d: PayslipDay): string {
  if (d.kind === "PRESENT") return d.no_checkout ? "Present · no check-out" : d.late ? "Present · late" : "Present";
  if (d.kind === "LEAVE") return `${titleCase(d.leave_type ?? "Leave")} leave${d.half_day ? " (½)" : ""}`;
  if (d.kind === "OFF") return "Weekly off";
  if (d.kind === "BEFORE_JOINING") return "Before joining";
  return "Absent";
}

function DayRow({ d }: { d: PayslipDay }) {
  return (
    <View style={{ flexDirection: "row", alignItems: "center", paddingVertical: 9, borderTopWidth: 1, borderTopColor: colors.border, gap: 8 }}>
      <View style={{ flex: 1 }}>
        <Text style={{ fontWeight: "700", color: colors.text }}>{dayName(d.date)}</Text>
        <Text style={font.tiny}>
          {what(d)}{d.check_in_at ? ` · ${time(d.check_in_at)} – ${time(d.check_out_at)}${d.minutes ? ` (${hm(d.minutes)})` : ""}` : ""}
          {d.mark ? ` · marked ${d.mark === "ABSENT" ? "unpaid" : d.mark === "HALF" ? "half day" : "full day"}` : ""}
        </Text>
      </View>
      <Text style={{ fontWeight: "800", color: d.counted === 0 ? colors.textFaint : colors.text }}>{counts(d.counted)}</Text>
    </View>
  );
}

function PayslipCard({ slip, startOpen }: { slip: Payslip; startOpen: boolean }) {
  const [open, setOpen] = useState(startOpen);
  return (
    <Card>
      <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: 10 }}>
        <View style={{ flex: 1 }}>
          <Text style={{ fontSize: 17, fontWeight: "800", color: colors.text }}>{slip.month_label}</Text>
          <Text style={font.small}>Paid on {fmtDate(slip.paid_at)}</Text>
        </View>
        <Badge tone="success">Paid</Badge>
      </View>
      <Text style={{ fontSize: 30, fontWeight: "800", color: colors.text, marginTop: 8 }}>{fmtMoney(slip.amount)}</Text>
      <Text style={[font.small, { marginTop: 2 }]}>
        {fmtMoney(slip.monthly_salary)} ÷ {slip.days_in_month} days × {slip.paid_days} paid days
      </Text>
      <Pressable onPress={() => setOpen((o) => !o)} accessibilityRole="button" accessibilityState={{ expanded: open }} style={{ marginTop: 12, minHeight: 44, justifyContent: "center" }}>
        <Text style={{ color: colors.brand600, fontWeight: "800" }}>{open ? "Hide day-wise attendance" : "Show day-wise attendance"}</Text>
      </Pressable>
      {open && <View>{(slip.days ?? []).map((d) => <DayRow key={d.date} d={d} />)}</View>}
    </Card>
  );
}

export default function Payslips() {
  const q = usePayslips();
  return (
    <Screen onRefresh={() => q.refetch()} refreshing={q.isRefetching && !q.isLoading}>
      {q.isLoading ? <ListSkeleton /> : q.isError ? <ErrorNote message={q.error.message} onRetry={() => q.refetch()} /> : q.data!.items.length === 0 ? (
        <Empty title="No payslips yet" text="Your payslip appears here once your salary has been paid." icon="cash-outline" />
      ) : (
        <View style={{ gap: 12 }}>
          {q.data!.items.map((s, i) => <PayslipCard key={s.id} slip={s} startOpen={i === 0} />)}
        </View>
      )}
    </Screen>
  );
}
