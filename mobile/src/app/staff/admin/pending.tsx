import { useMemo, useState } from "react";
import { FlatList, Linking, Pressable, Text, TextInput, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { usePending } from "@/api/adminHooks";
import { Chips, Empty, ErrorNote, ListSkeleton } from "@/components/ui";
import { PendingPill } from "@/components/PendingPill";
import { colors, font, radius } from "@/theme";

type Day = "0" | "1";

/** Live stores nobody has marked for the chosen day, with the POC's number so you can call. */
export default function Pending() {
  const [day, setDay] = useState<Day>("0");
  const [needle, setNeedle] = useState("");
  const q = usePending(Number(day));
  const shown = useMemo(() => {
    const n = needle.trim().toLowerCase();
    return (q.data?.items ?? []).filter((s) => !n || `${s.name} ${s.external_code} ${s.city ?? ""} ${s.state ?? ""} ${s.poc_name ?? ""} ${s.region_name ?? ""}`.toLowerCase().includes(n));
  }, [q.data, needle]);

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
          <View style={{ gap: 12, marginBottom: 4 }}>
            <Chips<Day> options={[{ label: "Today", value: "0" }, { label: "Yesterday", value: "1" }]} value={day} onChange={setDay} />
            {q.data && (
              <View style={{ backgroundColor: colors.ink950, borderRadius: radius.xl, padding: 16 }}>
                <Text style={{ color: "rgba(255,255,255,0.65)", fontSize: 12 }}>{q.data.date_label}</Text>
                <Text style={{ color: colors.white, fontSize: 28, fontWeight: "800" }}>{q.data.pending} <Text style={{ fontSize: 15, color: "rgba(255,255,255,0.6)", fontWeight: "600" }}>of {q.data.live_stores} stores not marked</Text></Text>
              </View>
            )}
            <View style={{ flexDirection: "row", alignItems: "center", gap: 8, height: 48, borderRadius: radius.md, backgroundColor: colors.surface, borderWidth: 1.5, borderColor: colors.border, paddingHorizontal: 12 }}>
              <Ionicons name="search" size={18} color={colors.textFaint} />
              <TextInput value={needle} onChangeText={setNeedle} placeholder="Search store, city, POC or region" placeholderTextColor={colors.textFaint} accessibilityLabel="Search" style={{ flex: 1, fontSize: 16, color: colors.text }} />
            </View>
          </View>
        }
        ListEmptyComponent={q.isLoading ? <ListSkeleton /> : q.isError ? <ErrorNote message={q.error.message} onRetry={() => q.refetch()} /> : <Empty title="Everything is marked" text="No live store is waiting for an entry." />}
        renderItem={({ item: s }) => (
          <View style={{ backgroundColor: colors.surface, borderRadius: radius.lg, borderWidth: 1, borderColor: colors.border, padding: 14, gap: 6 }}>
            <View style={{ flexDirection: "row", alignItems: "flex-start", justifyContent: "space-between", gap: 10 }}>
              <Text style={{ flex: 1, fontSize: 15, fontWeight: "700", color: colors.text }}>{s.name}</Text>
              <PendingPill days={s.pending_days} />
            </View>
            <Text numberOfLines={1} style={font.small}>{s.external_code} · {[s.city, s.state].filter(Boolean).join(", ")}{s.region_name ? ` · ${s.region_name}` : ""}</Text>
            {s.poc_name ? (
              <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginTop: 4 }}>
                <Text style={{ color: colors.text }}>POC: {s.poc_name}</Text>
                {s.poc_number ? (
                  <Pressable onPress={() => Linking.openURL(`tel:${s.poc_number!.replace(/[^\d+]/g, "")}`)} accessibilityRole="button" accessibilityLabel={`Call ${s.poc_name}`} style={{ flexDirection: "row", alignItems: "center", gap: 6, minHeight: 36, paddingHorizontal: 12, borderRadius: radius.pill, backgroundColor: colors.brand50 }}>
                    <Ionicons name="call-outline" size={16} color={colors.brand600} />
                    <Text style={{ color: colors.brand600, fontWeight: "700" }}>Call</Text>
                  </Pressable>
                ) : null}
              </View>
            ) : null}
          </View>
        )}
      />
    </View>
  );
}
