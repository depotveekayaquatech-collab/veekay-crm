import { useMemo, useState } from "react";
import { FlatList, Pressable, Text, TextInput, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useInsights, usePerformance } from "@/api/adminHooks";
import type { PerformanceRow } from "@/api/admin";
import { Badge, Chips, Empty, ErrorNote, ListSkeleton, ProgressBar } from "@/components/ui";
import { fmtMonth, isoDate } from "@/lib/format";
import { colors, font, radius } from "@/theme";

const tone = (p: number) => (p >= 85 ? "success" : p >= 50 ? "warning" : "danger") as "success" | "warning" | "danger";
const bar = (p: number) => (p >= 85 ? "success" : p >= 50 ? "brand" : "danger") as "success" | "brand" | "danger";
const short = (iso: string) => new Date(`${iso}T00:00:00`).toLocaleDateString("en-IN", { day: "numeric", month: "short" });

function shiftMonth(month: string, by: number): string {
  const [y, m] = month.split("-").map(Number);
  const d = new Date(y, m - 1 + by, 1);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

function EmployeeCard({ r }: { r: PerformanceRow }) {
  const [open, setOpen] = useState(false);
  return (
    <Pressable onPress={() => setOpen((o) => !o)} accessibilityRole="button" accessibilityState={{ expanded: open }} accessibilityLabel={`${r.employee_name}, ${r.percent} percent`}
      style={{ backgroundColor: colors.surface, borderRadius: radius.lg, borderWidth: 1, borderColor: colors.border, padding: 14, gap: 8 }}>
      <View style={{ flexDirection: "row", alignItems: "flex-start", justifyContent: "space-between", gap: 10 }}>
        <View style={{ flex: 1 }}>
          <Text style={{ fontSize: 15, fontWeight: "700", color: colors.text }}>{r.employee_name}</Text>
          <Text numberOfLines={1} style={font.small}>{r.employee_code}{r.region_name ? ` · ${r.region_name}` : ""} · {r.stores} stores</Text>
        </View>
        <Badge tone={tone(r.percent)}>{r.percent}%</Badge>
      </View>
      <ProgressBar value={r.percent / 100} tone={bar(r.percent)} />
      <Text style={font.small}>{r.done.toLocaleString("en-IN")} of {r.expected.toLocaleString("en-IN")} marked · {r.missing.toLocaleString("en-IN")} missing</Text>
      {open && (
        <View style={{ marginTop: 4 }}>
          <Text style={[font.tiny, { marginBottom: 6 }]}>Each day: the share of their stores marked for that day as of now, and their average from the 1st up to it.</Text>
          <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 6 }}>
            {r.daily.map((d) => {
              const [bg, fg] = d.percent >= 85 ? [colors.successSoft, colors.success] : d.percent >= 50 ? [colors.warningSoft, colors.warning] : [colors.dangerSoft, colors.danger];
              return (
                <View key={d.date} accessibilityLabel={`${short(d.date)}: ${d.percent} percent, average ${d.cumulative} percent`} style={{ backgroundColor: bg, borderRadius: 8, paddingHorizontal: 8, paddingVertical: 5, alignItems: "center", minWidth: 58 }}>
                  <Text style={{ color: fg, fontSize: 10, opacity: 0.8 }}>{short(d.date)}</Text>
                  <Text style={{ color: fg, fontSize: 13, fontWeight: "800" }}>{d.percent}%</Text>
                  <Text style={{ color: fg, fontSize: 10, opacity: 0.8 }}>avg {d.cumulative}%</Text>
                </View>
              );
            })}
          </View>
        </View>
      )}
      <View style={{ alignSelf: "flex-end" }}><Ionicons name={open ? "chevron-up" : "chevron-down"} size={16} color={colors.textFaint} /></View>
    </Pressable>
  );
}

/** Each employee's share of the entries they should have marked this month (1st to yesterday), recounted from the entries every time the screen opens. */
export default function Performance() {
  const ins = useInsights(true);
  const platforms = ins.data?.platforms ?? [];
  const [picked, setPicked] = useState("");
  const partner = platforms.some((p) => p.slug === picked) ? picked : (platforms[0]?.slug ?? "");
  const [month, setMonth] = useState("");                       // "" = the server's default: the month of yesterday
  const [needle, setNeedle] = useState("");
  const [behind, setBehind] = useState(false);
  const q = usePerformance(partner, month);
  const d = q.data;
  const thisMonth = isoDate(new Date()).slice(0, 7);
  const shown = d?.month ?? month;

  const rows = useMemo(() => {
    const n = needle.trim().toLowerCase();
    return (d?.employees ?? []).filter((e) => (!behind || e.percent < 50) && (!n || `${e.employee_name} ${e.employee_code} ${e.region_name ?? ""}`.toLowerCase().includes(n)));
  }, [d, needle, behind]);

  const header = (
    <View style={{ gap: 12, marginBottom: 4 }}>
      {platforms.length > 1 && <Chips options={platforms.map((p) => ({ label: p.label, value: p.slug }))} value={partner} onChange={(v) => { setPicked(v); }} />}
      <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between", backgroundColor: colors.surface, borderRadius: radius.lg, borderWidth: 1, borderColor: colors.border, paddingHorizontal: 8, height: 52 }}>
        <Pressable disabled={!shown} onPress={() => setMonth(shiftMonth(shown, -1))} accessibilityRole="button" accessibilityLabel="Previous month" hitSlop={10} style={{ padding: 8 }}><Ionicons name="chevron-back" size={20} color={colors.text} /></Pressable>
        <Text style={{ fontSize: 16, fontWeight: "800", color: colors.text }}>{shown ? fmtMonth(`${shown}-01`) : "…"}</Text>
        <Pressable disabled={!shown || shown >= thisMonth} onPress={() => setMonth(shiftMonth(shown, 1))} accessibilityRole="button" accessibilityLabel="Next month" hitSlop={10} style={{ padding: 8, opacity: !shown || shown >= thisMonth ? 0.3 : 1 }}><Ionicons name="chevron-forward" size={20} color={colors.text} /></Pressable>
      </View>
      {d && (
        <View style={{ backgroundColor: colors.ink950, borderRadius: radius.xl, padding: 16 }}>
          <Text style={{ color: "rgba(255,255,255,0.65)", fontSize: 12 }}>{d.partner_label} · team average</Text>
          <Text style={{ color: colors.white, fontSize: 32, fontWeight: "800" }}>{d.summary.percent}%</Text>
          <Text style={{ color: "rgba(255,255,255,0.7)", fontSize: 13, marginTop: 2 }}>
            {d.days === 0 ? "No day of this month has finished yet." : `${d.summary.done.toLocaleString("en-IN")} of ${d.summary.expected.toLocaleString("en-IN")} entries · ${short(d.from!)} to ${short(d.as_of!)} · ${d.summary.below_50} under 50%`}
          </Text>
        </View>
      )}
      <View style={{ flexDirection: "row", alignItems: "center", gap: 8, height: 48, borderRadius: radius.md, backgroundColor: colors.surface, borderWidth: 1.5, borderColor: colors.border, paddingHorizontal: 12 }}>
        <Ionicons name="search" size={18} color={colors.textFaint} />
        <TextInput value={needle} onChangeText={setNeedle} placeholder="Search name, ID or region" placeholderTextColor={colors.textFaint} accessibilityLabel="Search" style={{ flex: 1, fontSize: 16, color: colors.text }} />
      </View>
      <Chips<"all" | "behind"> options={[{ label: "Everyone", value: "all" }, { label: "Under 50%", value: "behind" }]} value={behind ? "behind" : "all"} onChange={(v) => setBehind(v === "behind")} />
    </View>
  );

  return (
    <View style={{ flex: 1, backgroundColor: colors.surfaceSubtle }}>
      <FlatList
        data={rows}
        keyExtractor={(r) => r.employee_id}
        keyboardShouldPersistTaps="handled"
        onRefresh={() => q.refetch()}
        refreshing={q.isRefetching && !q.isLoading}
        contentContainerStyle={{ padding: 16, paddingBottom: 40, gap: 10 }}
        ListHeaderComponent={header}
        ListEmptyComponent={q.isLoading || ins.isLoading ? <ListSkeleton /> : q.isError ? <ErrorNote message={q.error.message} onRetry={() => q.refetch()} /> : <Empty title="Nobody matches" text="Try another name or filter." />}
        renderItem={({ item }) => <EmployeeCard r={item} />}
      />
    </View>
  );
}
