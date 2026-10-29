import { useMemo, useState } from "react";
import { FlatList, Pressable, Text, TextInput, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import { useAuth } from "@/auth/AuthProvider";
import { useInsights, usePerformance, usePerformancePending } from "@/api/adminHooks";
import type { PerformanceRow } from "@/api/admin";
import { Badge, Chips, Empty, ErrorNote, ListSkeleton, ProgressBar } from "@/components/ui";
import { fmtMonth, isoDate } from "@/lib/format";
import { colors, font, radius } from "@/theme";

// Green only when nothing is missing (100%); yellow from 99.9% down to 70%; red below 70%.
const tone = (p: number) => (p >= 100 ? "success" : p >= 70 ? "warning" : "danger") as "success" | "warning" | "danger";
const bar = (p: number) => (p >= 100 ? "success" : p >= 70 ? "warning" : "danger") as "success" | "warning" | "danger";
const short = (iso: string) => new Date(`${iso}T00:00:00`).toLocaleDateString("en-IN", { day: "numeric", month: "short" });

function shiftMonth(month: string, by: number): string {
  const [y, m] = month.split("-").map(Number);
  const d = new Date(y, m - 1 + by, 1);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

/** The stores still to mark from the 1st up to the tapped day: marking them all brings the person to 100% as of that day. A store opens its calendar to mark. */
function PendingForDay({ partner, employeeId, date }: { partner: string; employeeId: string; date: string }) {
  const router = useRouter();
  const q = usePerformancePending(partner, employeeId, date);
  if (q.isLoading) return <ListSkeleton rows={2} />;
  if (q.isError || !q.data) return <ErrorNote message={q.error?.message ?? "Couldn't load the stores."} onRetry={() => q.refetch()} />;
  const d = q.data;
  const lastMonth = date.slice(0, 7) !== isoDate(new Date()).slice(0, 7);
  const range = d.from && d.from !== date ? `${short(d.from)} to ${short(date)}` : short(date);
  return (
    <View style={{ marginTop: 10, gap: 8, padding: 10, borderRadius: radius.md, backgroundColor: colors.surfaceSubtle, borderWidth: 1, borderColor: colors.border }}>
      <Text style={{ fontSize: 14, fontWeight: "800", color: colors.text }}>
        {d.stores.length === 0 ? `${range}: nothing left to mark, 100% as of ${short(date)}` : `${range}: ${d.missing_total} day${d.missing_total === 1 ? "" : "s"} still to mark in ${d.stores.length} store${d.stores.length === 1 ? "" : "s"}`}
      </Text>
      {d.stores.length > 0 ? (
        <Text style={font.small}>
          {d.month_open ? "Tap a store to open it and mark its missing days." : "This month is closed for entries: you can look at these stores, only an admin can mark them now."}
        </Text>
      ) : null}
      {d.stores.map((st) => (
        <Pressable
          key={st.store_id}
          disabled={!st.can_open}
          onPress={() => router.push(`/staff/mark/${st.store_id}?${lastMonth ? "month=last&" : ""}day=${st.missing_dates[0]}` as never)}
          accessibilityRole="button"
          accessibilityLabel={`${st.store_name}, ${st.missing_days} days missing`}
          android_ripple={{ color: colors.brand100 }}
          style={{ backgroundColor: colors.surface, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, padding: 10, gap: 2, opacity: st.can_open ? 1 : 0.6 }}
        >
          <View style={{ flexDirection: "row", justifyContent: "space-between", gap: 8 }}>
            <Text numberOfLines={1} style={{ flex: 1, fontSize: 14, fontWeight: "700", color: colors.text }}>{st.store_name}</Text>
            <Badge tone="warning">{st.missing_days} day{st.missing_days === 1 ? "" : "s"}</Badge>
          </View>
          <Text numberOfLines={1} style={font.small}>{[st.external_code, st.city, st.state].filter(Boolean).join(" · ")}</Text>
          <Text style={font.small}>Missing: {st.missing_dates.map(short).join(", ")}</Text>
        </Pressable>
      ))}
    </View>
  );
}

function EmployeeCard({ r, partner, defaultOpen = false }: { r: PerformanceRow; partner: string; defaultOpen?: boolean }) {
  const [open, setOpen] = useState(defaultOpen);
  const [day, setDay] = useState<string | null>(null);
  return (
    <Pressable onPress={() => setOpen((o) => !o)} accessibilityRole="button" accessibilityState={{ expanded: open }} accessibilityLabel={`${r.employee_name}, ${r.percent} percent`}
      style={{ backgroundColor: colors.surface, borderRadius: radius.lg, borderWidth: 1, borderColor: colors.border, padding: 14, gap: 8 }}>
      <View style={{ flexDirection: "row", alignItems: "flex-start", justifyContent: "space-between", gap: 10 }}>
        <View style={{ flex: 1 }}>
          <Text style={{ fontSize: 15, fontWeight: "700", color: colors.text }}>{r.employee_name}</Text>
          <Text numberOfLines={1} style={font.small}>{r.employee_code}{r.region_name ? ` · ${r.region_name}` : ""} · {r.stores} stores{r.is_team_lead ? " · Team Lead" : ""}</Text>
          {(r.is_team_lead || (r.corrected ?? 0) > 0) && <Text style={{ fontSize: 12, fontWeight: "700", color: colors.brand700 }}>{(r.corrected ?? 0).toLocaleString("en-IN")} {r.corrected === 1 ? "entry" : "entries"} corrected</Text>}
        </View>
        {r.no_stores ? <Badge tone="neutral">No stores</Badge> : <Badge tone={tone(r.percent)}>{r.percent}%</Badge>}
      </View>
      {r.no_stores ? (
        <Text style={font.small}>{(r.entries_made ?? 0).toLocaleString("en-IN")} entries made this month · no store of their own, so no percentage</Text>
      ) : (
        <>
          <ProgressBar value={r.percent / 100} tone={bar(r.percent)} />
          <Text style={font.small}>{r.done.toLocaleString("en-IN")} of {r.expected.toLocaleString("en-IN")} of their stores covered by anyone · {r.missing.toLocaleString("en-IN")} missing · {(r.entries_made ?? 0).toLocaleString("en-IN")} typed in by them</Text>
        </>
      )}
      {open && !r.no_stores && (
        <View style={{ marginTop: 4 }}>
          <Text style={[font.tiny, { marginBottom: 6 }]}>Each day: the share of their stores marked for that day as of now, and their average from the 1st up to it.</Text>
          <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 6 }}>
            {r.daily.map((d) => {
              const [bg, fg] = d.percent >= 100 ? [colors.successSoft, colors.success] : d.percent >= 70 ? [colors.warningSoft, colors.warning] : [colors.dangerSoft, colors.danger];
              const picked = day === d.date;
              return (
                <Pressable key={d.date} onPress={() => setDay(picked ? null : d.date)} accessibilityRole="button" accessibilityState={{ selected: picked }}
                  accessibilityLabel={`${short(d.date)}: ${d.percent} percent, average ${d.cumulative} percent. Tap to see the stores still to mark up to this day`}
                  style={{ backgroundColor: bg, borderRadius: 8, paddingHorizontal: 8, paddingVertical: 5, alignItems: "center", minWidth: 58, borderWidth: picked ? 2 : 0, borderColor: colors.brand600 }}>
                  <Text style={{ color: fg, fontSize: 10, opacity: 0.8 }}>{short(d.date)}</Text>
                  <Text style={{ color: fg, fontSize: 13, fontWeight: "800" }}>{d.percent}%</Text>
                  <Text style={{ color: fg, fontSize: 10, opacity: 0.8 }}>avg {d.cumulative}%</Text>
                </Pressable>
              );
            })}
          </View>
          <Text style={[font.tiny, { marginTop: 6 }]}>Tap a day to see every store still to mark from the 1st up to that day.</Text>
          {day && r.daily.some((x) => x.date === day) ? <PendingForDay partner={partner} employeeId={r.employee_id} date={day} /> : null}
        </View>
      )}
      {!r.no_stores && <View style={{ alignSelf: "flex-end" }}><Ionicons name={open ? "chevron-up" : "chevron-down"} size={16} color={colors.textFaint} /></View>}
    </Pressable>
  );
}

/** Each employee's share of the entries they should have marked this month (1st to yesterday), recounted from the entries every time the screen opens. */
export default function Performance() {
  const { staff, hasPermission } = useAuth();
  // Everyone with the orders screens sees this: an employee only themselves, a Team Lead their team, the daily overview everyone (the server decides).
  const overview = hasPermission("orders.overview");
  const ins = useInsights(overview);
  const platforms = overview ? (ins.data?.platforms ?? []) : staff?.platform_slug ? [{ slug: staff.platform_slug, label: staff.platform_label ?? staff.platform_slug }] : [];
  const [picked, setPicked] = useState("");
  const partner = platforms.some((p) => p.slug === picked) ? picked : (platforms[0]?.slug ?? "");
  const [month, setMonth] = useState("");                       // "" = the server's default: the month of yesterday
  const [needle, setNeedle] = useState("");
  const [behind, setBehind] = useState(false);
  const q = usePerformance(partner, month);
  const d = q.data;
  const alone = d?.view === "self";                          // an employee sees only themselves: no search, no team filters
  const thisMonth = isoDate(new Date()).slice(0, 7);
  const shown = d?.month ?? month;

  const rows = useMemo(() => {
    const n = needle.trim().toLowerCase();
    return (d?.employees ?? []).filter((e) => (!behind || (!e.no_stores && e.percent < 50)) && (!n || `${e.employee_name} ${e.employee_code} ${e.region_name ?? ""}`.toLowerCase().includes(n)));
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
          <Text style={{ color: "rgba(255,255,255,0.65)", fontSize: 12 }}>{d.partner_label} · {alone ? "your performance" : d.view === "team" ? "your team, each store-day counted once" : "overall, each store-day counted once"}</Text>
          <Text style={{ color: colors.white, fontSize: 32, fontWeight: "800" }}>{d.summary.percent}%</Text>
          <Text style={{ color: "rgba(255,255,255,0.7)", fontSize: 13, marginTop: 2 }}>
            {d.days === 0 ? "No day of this month has finished yet." : `${d.summary.done.toLocaleString("en-IN")} of ${d.summary.expected.toLocaleString("en-IN")} entries · ${short(d.from!)} to ${short(d.as_of!)}${alone ? "" : ` · ${d.summary.below_50} under 50%`}`}
          </Text>
        </View>
      )}
      {alone ? null : (
        <>
          <View style={{ flexDirection: "row", alignItems: "center", gap: 8, height: 48, borderRadius: radius.md, backgroundColor: colors.surface, borderWidth: 1.5, borderColor: colors.border, paddingHorizontal: 12 }}>
            <Ionicons name="search" size={18} color={colors.textFaint} />
            <TextInput value={needle} onChangeText={setNeedle} placeholder="Search name, ID or region" placeholderTextColor={colors.textFaint} accessibilityLabel="Search" style={{ flex: 1, fontSize: 16, color: colors.text }} />
          </View>
          <Chips<"all" | "behind"> options={[{ label: "Everyone", value: "all" }, { label: "Under 50%", value: "behind" }]} value={behind ? "behind" : "all"} onChange={(v) => setBehind(v === "behind")} />
        </>
      )}
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
        renderItem={({ item }) => <EmployeeCard r={item} partner={partner} defaultOpen={alone} />}
      />
    </View>
  );
}
