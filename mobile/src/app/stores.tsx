import { useMemo, useState } from "react";
import { FlatList, Pressable, Text, TextInput, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import { useBottles, useStores } from "@/api/hooks";
import { Empty, ErrorNote, ListSkeleton } from "@/components/ui";
import { colors, font, radius } from "@/theme";

export default function Stores() {
  const router = useRouter();
  const stores = useStores();
  const bottles = useBottles({ page_size: 1 });
  const [needle, setNeedle] = useState("");
  const shown = useMemo(() => {
    const n = needle.trim().toLowerCase();
    return (stores.data ?? []).filter((s) => !n || `${s.name} ${s.code} ${s.city ?? ""} ${s.state ?? ""}`.toLowerCase().includes(n));
  }, [stores.data, needle]);

  return (
    <View style={{ flex: 1, backgroundColor: colors.surfaceSubtle }}>
      <View style={{ padding: 16, paddingBottom: 8, gap: 10 }}>
        <Text style={font.small}>{stores.data ? `${stores.data.length} stores` : "Loading…"}. Tap one to see its orders.</Text>
        <View style={{ flexDirection: "row", alignItems: "center", gap: 8, height: 48, borderRadius: radius.md, backgroundColor: colors.surface, borderWidth: 1.5, borderColor: colors.border, paddingHorizontal: 12 }}>
          <Ionicons name="search" size={18} color={colors.textFaint} />
          <TextInput value={needle} onChangeText={setNeedle} placeholder="Search by name, code or city" placeholderTextColor={colors.textFaint} accessibilityLabel="Search stores" style={{ flex: 1, fontSize: 16, color: colors.text }} />
        </View>
      </View>
      {stores.isLoading ? <View style={{ padding: 16 }}><ListSkeleton /></View> : stores.isError ? <View style={{ padding: 16 }}><ErrorNote message={stores.error.message} onRetry={() => stores.refetch()} /></View> : (
        <FlatList
          data={shown}
          keyExtractor={(s) => s.id}
          keyboardShouldPersistTaps="handled"
          contentContainerStyle={{ paddingHorizontal: 16, paddingBottom: 32 }}
          ListEmptyComponent={<Empty title="No store matches" text="Try a different name, code or city." />}
          ItemSeparatorComponent={() => <View style={{ height: 1, backgroundColor: colors.border }} />}
          renderItem={({ item: s, index }) => (
            <Pressable
              onPress={() => router.push({ pathname: "/orders", params: { store: s.id } })}
              accessibilityRole="button"
              android_ripple={{ color: colors.brand100 }}
              style={{ minHeight: 64, paddingHorizontal: 16, paddingVertical: 12, backgroundColor: colors.surface, flexDirection: "row", alignItems: "center", gap: 12, borderTopLeftRadius: index === 0 ? radius.lg : 0, borderTopRightRadius: index === 0 ? radius.lg : 0, borderBottomLeftRadius: index === shown.length - 1 ? radius.lg : 0, borderBottomRightRadius: index === shown.length - 1 ? radius.lg : 0 }}
            >
              <View style={{ flex: 1 }}>
                <Text numberOfLines={1} style={{ fontSize: 15, fontWeight: "600", color: colors.text }}>{s.name}</Text>
                <Text numberOfLines={1} style={font.small}>{s.platform ? `${s.platform[0].toUpperCase()}${s.platform.slice(1)} · ` : ""}{s.code}{s.city ? ` · ${s.city}` : ""}{s.state ? `, ${s.state}` : ""}</Text>
              </View>
              <Text style={{ fontSize: 12, fontWeight: "600", color: colors.textMuted }}>{bottles.data?.per_store[s.id] ?? 0} bottles</Text>
            </Pressable>
          )}
        />
      )}
    </View>
  );
}
