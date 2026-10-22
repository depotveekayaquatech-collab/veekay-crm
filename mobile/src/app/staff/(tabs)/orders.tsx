import { useCallback, useMemo, useState } from "react";
import { FlatList, Pressable, Text, TextInput, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useFocusEffect, useRouter } from "expo-router";
import { useMyStores } from "@/api/staffHooks";
import { Chips, Empty, ErrorNote, ListSkeleton } from "@/components/ui";
import { PendingPill } from "@/components/PendingPill";
import { VendorPicker, vendorKey, vendorsOf } from "@/components/VendorPicker";
import { fmtDate, fmtNumber } from "@/lib/format";
import { colors, font, radius } from "@/theme";

type Filter = "all" | "pending" | "done" | "lastmonth";
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
  const [vendor, setVendor] = useState("");   // vendorKey of the chosen vendor, "" = all vendors

  // Coming back from a store's page (or another tab) always shows the latest marks.
  const { refetch } = q;
  useFocusEffect(useCallback(() => { void refetch(); }, [refetch]));

  const stores = useMemo(() => (q.data ?? []).filter((s) => s.status === "LIVE"), [q.data]);
  const serverToday = q.data?.[0]?.today;
  // For the first days of a month, last month can still be completed: which stores still have days to fill
  const lastOpenUntil = stores.find((s) => s.last_month_open_until)?.last_month_open_until ?? null;
  const lastMissing = lastOpenUntil ? stores.filter((s) => (s.last_month_missing ?? 0) > 0) : [];
  const dayIso = serverToday ? (day === "today" ? serverToday : shift(serverToday, -1)) : undefined;
  const countOf = useCallback((s: { today_count: number | null; yesterday_count?: number | null }) => (day === "today" ? s.today_count : s.yesterday_count ?? null), [day]);
  const done = stores.filter((s) => countOf(s) !== null).length;
  const percent = stores.length ? Math.round((done / stores.length) * 100) : 0;

  // Vendor filter: pick a vendor to see all of its stores; the chips below then count that vendor's stores only
  const vendors = useMemo(() => vendorsOf(stores), [stores]);
  const scope = useMemo(() => (vendor ? stores.filter((s) => vendorKey(s.vendor_name) === vendor) : stores), [stores, vendor]);
  const scopeDone = scope.filter((s) => countOf(s) !== null).length;
  const pickVendor = (key: string) => { setVendor(key); if (key) setFilter("all"); };   // "all" so none of its stores are hidden

  const shown = useMemo(() => {
    const n = needle.trim().toLowerCase();
    if (filter === "lastmonth") {
      return lastMissing
        .filter((s) => !vendor || vendorKey(s.vendor_name) === vendor)
        .filter((s) => !n || `${s.name} ${s.external_code} ${s.city ?? ""} ${s.state ?? ""} ${s.vendor_name ?? ""}`.toLowerCase().includes(n))
        .sort((a, b) => (b.last_month_missing ?? 0) - (a.last_month_missing ?? 0) || a.name.localeCompare(b.name));
    }
    const list = scope
      .filter((s) => (filter === "all" ? true : filter === "done" ? countOf(s) !== null : countOf(s) === null))
      .filter((s) => !n || `${s.name} ${s.external_code} ${s.city ?? ""} ${s.state ?? ""} ${s.vendor_name ?? ""}`.toLowerCase().includes(n));
    // the pending list starts with the stores that have waited longest
    return filter === "pending" ? [...list].sort((a, b) => (b.pending_days ?? 0) - (a.pending_days ?? 0) || a.name.localeCompare(b.name)) : list;
  }, [scope, filter, needle, countOf, lastMissing, vendor]);

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
            <Pressable onPress={() => router.push("/staff/entries")} accessibilityRole="button" accessibilityLabel="See everything you entered in the last days" android_ripple={{ color: colors.brand100 }}
              style={{ flexDirection: "row", alignItems: "center", gap: 10, minHeight: 48, paddingHorizontal: 14, borderRadius: radius.md, backgroundColor: colors.brand50 }}>
              <Ionicons name="checkmark-done-outline" size={20} color={colors.brand600} />
              <Text style={{ flex: 1, fontWeight: "700", color: colors.brand700 }}>My entries: check what you saved in the last days</Text>
              <Ionicons name="chevron-forward" size={18} color={colors.brand600} />
            </Pressable>
            {lastOpenUntil && lastMissing.length > 0 ? (
              <Pressable onPress={() => setFilter("lastmonth")} accessibilityRole="button" android_ripple={{ color: colors.brand100 }}
                style={{ flexDirection: "row", alignItems: "center", gap: 10, padding: 14, borderRadius: radius.md, backgroundColor: colors.warningSoft }}>
                <Ionicons name="calendar-outline" size={22} color={colors.warning} />
                <View style={{ flex: 1 }}>
                  <Text style={{ fontWeight: "800", color: colors.warning }}>Last month is still open until {fmtDate(lastOpenUntil)}</Text>
                  <Text style={font.small}>{lastMissing.length} store{lastMissing.length === 1 ? " has" : "s have"} days of last month with no entry yet. Tap to fill them.</Text>
                </View>
                <Ionicons name="chevron-forward" size={18} color={colors.warning} />
              </Pressable>
            ) : null}
            <Chips<Day> options={[{ label: "Today", value: "today" }, { label: "Yesterday", value: "yesterday" }]} value={day} onChange={setDay} />
            <VendorPicker vendors={vendors} value={vendor} onChange={pickVendor} />
            <View style={{ flexDirection: "row", alignItems: "center", gap: 8, height: 48, borderRadius: radius.md, backgroundColor: colors.surface, borderWidth: 1.5, borderColor: colors.border, paddingHorizontal: 12 }}>
              <Ionicons name="search" size={18} color={colors.textFaint} />
              <TextInput value={needle} onChangeText={setNeedle} placeholder="Search store, code, city or vendor" placeholderTextColor={colors.textFaint} accessibilityLabel="Search stores" style={{ flex: 1, fontSize: 16, color: colors.text }} />
            </View>
            <Chips<Filter> options={[{ label: `Pending ${scope.length - scopeDone}`, value: "pending" }, { label: `Done ${scopeDone}`, value: "done" }, { label: `All ${scope.length}`, value: "all" }, ...(lastOpenUntil ? [{ label: `Last month ${lastMissing.length}`, value: "lastmonth" as Filter }] : [])]} value={filter} onChange={setFilter} />
          </View>
        }
        ListEmptyComponent={
          q.isLoading ? <ListSkeleton /> : q.isError ? <ErrorNote message={q.error.message} onRetry={() => q.refetch()} /> : (
            <Empty title={filter === "lastmonth" && !needle ? "Last month is complete" : filter === "pending" && !needle ? `All ${vendor ? "of this vendor's " : ""}stores are marked for ${day}` : "No store matches"} text={filter === "lastmonth" && !needle ? "Every store has all its days of last month." : filter === "pending" && !needle ? "Nice work. You can still mark earlier days of this month from a store's page." : "Try a different filter or search."} />
          )
        }
        renderItem={({ item: s }) => (
          <Pressable
            onPress={() => router.push(filter === "lastmonth" ? `/staff/mark/${s.id}?month=last` : dayIso ? `/staff/mark/${s.id}?day=${dayIso}` : `/staff/mark/${s.id}`)}
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
              <Text numberOfLines={1} style={font.small}>{s.external_code}{s.city ? ` · ${s.city}` : ""}{!vendor && s.vendor_name ? ` · ${s.vendor_name}` : ""}</Text>
              <Text numberOfLines={1} style={font.tiny}>This month {fmtNumber(s.month_bottles ?? 0)} · Last month {fmtNumber(s.last_month_bottles ?? 0)} bottles</Text>
              {filter === "lastmonth" ? (
                <View style={{ marginTop: 6, alignSelf: "flex-start", flexDirection: "row", alignItems: "center", gap: 6, paddingHorizontal: 10, paddingVertical: 4, borderRadius: radius.pill, backgroundColor: colors.warningSoft }}>
                  <View style={{ width: 6, height: 6, borderRadius: 3, backgroundColor: colors.warning }} />
                  <Text style={{ fontSize: 12, fontWeight: "800", color: colors.warning }}>{s.last_month_missing} day{s.last_month_missing === 1 ? "" : "s"} of last month missing</Text>
                </View>
              ) : countOf(s) === null ? <View style={{ marginTop: 6 }}><PendingPill days={s.pending_days ?? 0} /></View> : null}
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
