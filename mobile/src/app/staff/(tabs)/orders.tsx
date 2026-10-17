import { useCallback, useMemo, useState } from "react";
import { FlatList, Pressable, Text, TextInput, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useFocusEffect, useRouter } from "expo-router";
import { useMyStores } from "@/api/staffHooks";
import { Chips, Empty, ErrorNote, ListSkeleton } from "@/components/ui";
import { colors, font, radius } from "@/theme";

type Filter = "all" | "pending" | "done";
type Day = "today" | "yesterday";

/** The server's own calendar day (it decides what "today" means, not the phone), one day earlier when asked. */
function shift(iso: string, days: number): string {
  const d = new Date(`${iso}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}
const short = (iso: string) => new Date(`${iso}T00:00:00`).toLocaleDateString("en-IN", { weekday: "short", day: "numeric", month: "short" });

export default function Orders() {
  const router = useRouter();
  const q = useMyStores();
  const [needle, setNeedle] = useState("");
  const [filter, setFilter] = useState<Filter>("pending");
  const [day, setDay] = useState<Day>("today");

  // Coming back from a store's page (or another tab) always shows the latest marks.
  const { refetch } = q;
  useFocusEffect(useCallback(() => { void refetch(); }, [refetch]));

  const stores = useMemo(() => (q.data ?? []).filter((s) => s.status === "LIVE"), [q.data]);
  const serverToday = q.data?.[0]?.today;
  const dayIso = serverToday ? (day === "today" ? serverToday : shift(serverToday, -1)) : undefined;
  const countOf = useCallback((s: { today_count: number | null; yesterday_count?: number | null }) => (day === "today" ? s.today_count : s.yesterday_count ?? null), [day]);
  const done = stores.filter((s) => countOf(s) !== null).length;
  const percent = stores.length ? Math.round((done / stores.length) * 100) : 0;

  const shown = useMemo(() => {
    const n = needle.trim().toLowerCase();
    return stores
      .filter((s) => (filter === "all" ? true : filter === "done" ? countOf(s) !== null : countOf(s) === null))
      .filter((s) => !n || `${s.name} ${s.external_code} ${s.city ?? ""} ${s.state ?? ""}`.toLowerCase().includes(n));
  }, [stores, filter, needle, countOf]);

  return (
    <View style={{ flex: 1, backgroundColor: colors.surfaceSubtle }}>
      <FlatList
        data={shown}
        keyExtractor={(s) => s.id}
        keyboardShouldPersistTaps="handled"
        onRefresh={() => q.refetch()}
        refreshing={q.isRefetching && !q.isLoading}
        contentContainerStyle={{ padding: 16, paddingBottom: 40, gap: 10 }}
        ListHeaderComponent={
          <View style={{ gap: 14, marginBottom: 4 }}>
            {/* Today's progress, like a daily-goal card */}
            <View style={{ backgroundColor: colors.ink950, borderRadius: radius.xl, padding: 18 }}>
              <Text style={{ color: "rgba(255,255,255,0.65)", fontSize: 12 }}>{day === "today" ? "Today's" : "Yesterday's"} entries{dayIso ? ` · ${short(dayIso)}` : ""}</Text>
              <View style={{ flexDirection: "row", alignItems: "flex-end", justifyContent: "space-between", marginTop: 4 }}>
                <Text style={{ color: colors.white, fontSize: 30, fontWeight: "800" }}>{done}<Text style={{ fontSize: 16, color: "rgba(255,255,255,0.6)", fontWeight: "600" }}> / {stores.length} stores</Text></Text>
                <Text style={{ color: colors.aqua200, fontSize: 18, fontWeight: "800" }}>{percent}%</Text>
              </View>
              <View style={{ height: 8, borderRadius: 4, backgroundColor: "rgba(255,255,255,0.15)", marginTop: 12, overflow: "hidden" }}>
                <View style={{ height: 8, borderRadius: 4, backgroundColor: colors.brand500, width: `${percent}%` }} />
              </View>
            </View>
            <Chips<Day> options={[{ label: "Today", value: "today" }, { label: "Yesterday", value: "yesterday" }]} value={day} onChange={setDay} />
            <View style={{ flexDirection: "row", alignItems: "center", gap: 8, height: 48, borderRadius: radius.md, backgroundColor: colors.surface, borderWidth: 1.5, borderColor: colors.border, paddingHorizontal: 12 }}>
              <Ionicons name="search" size={18} color={colors.textFaint} />
              <TextInput value={needle} onChangeText={setNeedle} placeholder="Search store, code or city" placeholderTextColor={colors.textFaint} accessibilityLabel="Search stores" style={{ flex: 1, fontSize: 16, color: colors.text }} />
            </View>
            <Chips<Filter> options={[{ label: `Pending ${stores.length - done}`, value: "pending" }, { label: `Done ${done}`, value: "done" }, { label: "All", value: "all" }]} value={filter} onChange={setFilter} />
          </View>
        }
        ListEmptyComponent={
          q.isLoading ? <ListSkeleton /> : q.isError ? <ErrorNote message={q.error.message} onRetry={() => q.refetch()} /> : (
            <Empty title={filter === "pending" && !needle ? `All stores are marked for ${day}` : "No store matches"} text={filter === "pending" && !needle ? "Nice work. You can still mark earlier days of this month from a store's page." : "Try a different filter or search."} />
          )
        }
        renderItem={({ item: s }) => (
          <Pressable
            onPress={() => router.push(dayIso ? `/staff/mark/${s.id}?day=${dayIso}` : `/staff/mark/${s.id}`)}
            accessibilityRole="button"
            accessibilityLabel={`${s.name}, ${countOf(s) === null ? `not marked ${day}` : `marked ${countOf(s)} ${day}`}`}
            android_ripple={{ color: colors.brand100 }}
            style={{ backgroundColor: colors.surface, borderRadius: radius.lg, borderWidth: 1, borderColor: colors.border, padding: 14, flexDirection: "row", alignItems: "center", gap: 12 }}
          >
            <View style={{ width: 42, height: 42, borderRadius: 21, alignItems: "center", justifyContent: "center", backgroundColor: countOf(s) === null ? colors.warningSoft : colors.successSoft }}>
              <Ionicons name={countOf(s) === null ? "time-outline" : "checkmark"} size={22} color={countOf(s) === null ? colors.warning : colors.success} />
            </View>
            <View style={{ flex: 1 }}>
              <Text numberOfLines={1} style={{ fontSize: 15, fontWeight: "700", color: colors.text }}>{s.name}</Text>
              <Text numberOfLines={1} style={font.small}>{s.external_code}{s.city ? ` · ${s.city}` : ""}</Text>
            </View>
            {countOf(s) !== null ? (
              <View style={{ alignItems: "flex-end" }}><Text style={{ fontSize: 18, fontWeight: "800", color: colors.text }}>{countOf(s)}</Text><Text style={font.tiny}>{day}</Text></View>
            ) : (
              <Text style={{ fontSize: 13, fontWeight: "700", color: colors.brand600 }}>Mark</Text>
            )}
            <Ionicons name="chevron-forward" size={18} color={colors.textFaint} />
          </Pressable>
        )}
      />
    </View>
  );
}
