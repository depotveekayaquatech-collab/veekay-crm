import { useEffect, useMemo, useState } from "react";
import { FlatList, Modal, Pressable, Text, TextInput, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useStores } from "@/api/hooks";
import { colors, font, radius } from "@/theme";

export interface PickerStore { id: string; name: string; code: string; city?: string | null; state?: string | null }

/** Store chooser: a field that opens a searchable full-screen list (a login can have 50+ stores).
 * With a single store it is selected for you. A vendor / POC login lists its own stores; an employee screen passes the
 * employee's list in `stores` (while that list loads, pass `[]`, not undefined). */
export function StorePicker({ value, onChange, allLabel, label = "Store", stores: given }: { value: string; onChange: (id: string) => void; allLabel?: string; label?: string; stores?: PickerStore[] }) {
  const partner = useStores(given === undefined);
  const stores: PickerStore[] | undefined = given ?? partner.data;
  const insets = useSafeAreaInsets();
  const [open, setOpen] = useState(false);
  const [needle, setNeedle] = useState("");
  const only = stores && stores.length === 1 ? stores[0].id : null;

  useEffect(() => {
    if (only && value !== only) onChange(only);
  }, [only, value, onChange]);

  const current = stores?.find((x) => x.id === value);
  const shown = useMemo(() => {
    const n = needle.trim().toLowerCase();
    return (stores ?? []).filter((x) => !n || `${x.name} ${x.code} ${x.city ?? ""} ${x.state ?? ""}`.toLowerCase().includes(n));
  }, [stores, needle]);

  const close = () => { setOpen(false); setNeedle(""); };
  const pick = (id: string) => { onChange(id); close(); };

  return (
    <View style={{ gap: 6 }}>
      <Text style={{ fontSize: 13, fontWeight: "600", color: colors.text }}>{label}</Text>
      <Pressable
        onPress={() => setOpen(true)}
        disabled={!!only}
        accessibilityRole="button"
        accessibilityLabel={`${label}: ${current ? current.name : allLabel ?? "not chosen"}. Double tap to change.`}
        style={{ minHeight: 52, borderRadius: radius.md, borderWidth: 1.5, borderColor: colors.border, backgroundColor: only ? colors.surfaceSubtle : colors.surface, paddingHorizontal: 14, flexDirection: "row", alignItems: "center", gap: 8 }}
      >
        <Text numberOfLines={1} style={{ flex: 1, fontSize: 16, color: current || !value ? colors.text : colors.textFaint }}>
          {current ? current.name : allLabel ?? "Choose a store…"}
        </Text>
        {!only && <Ionicons name="chevron-down" size={18} color={colors.textFaint} />}
      </Pressable>

      <Modal visible={open} animationType="slide" onRequestClose={close} statusBarTranslucent>
        <View style={{ flex: 1, backgroundColor: colors.surface, paddingTop: insets.top }}>
          <View style={{ flexDirection: "row", alignItems: "center", gap: 8, padding: 12, borderBottomWidth: 1, borderBottomColor: colors.border }}>
            <View style={{ flex: 1, flexDirection: "row", alignItems: "center", gap: 8, height: 46, borderRadius: radius.md, backgroundColor: colors.surfaceSubtle, paddingHorizontal: 12 }}>
              <Ionicons name="search" size={18} color={colors.textFaint} />
              <TextInput
                autoFocus
                value={needle}
                onChangeText={setNeedle}
                placeholder="Search by name, code or city"
                placeholderTextColor={colors.textFaint}
                accessibilityLabel="Search stores"
                returnKeyType="search"
                style={{ flex: 1, fontSize: 16, color: colors.text }}
              />
            </View>
            <Pressable onPress={close} accessibilityRole="button" hitSlop={8} style={{ paddingHorizontal: 6, minHeight: 44, justifyContent: "center" }}>
              <Text style={{ color: colors.brand600, fontWeight: "700", fontSize: 16 }}>Cancel</Text>
            </Pressable>
          </View>
          <FlatList
            data={shown}
            keyExtractor={(x) => x.id}
            keyboardShouldPersistTaps="handled"
            contentContainerStyle={{ paddingBottom: insets.bottom }}
            ListHeaderComponent={allLabel !== undefined && !needle.trim() ? (
              <Row title={allLabel} selected={value === ""} onPress={() => pick("")} />
            ) : null}
            ListEmptyComponent={<Text style={[font.small, { textAlign: "center", padding: 40 }]}>No store matches “{needle}”.</Text>}
            renderItem={({ item }) => (
              <Row
                title={item.name}
                sub={`${item.code}${item.city ? ` · ${item.city}` : ""}${item.state ? `, ${item.state}` : ""}`}
                selected={item.id === value}
                onPress={() => pick(item.id)}
              />
            )}
          />
        </View>
      </Modal>
    </View>
  );
}

function Row({ title, sub, selected, onPress }: { title: string; sub?: string; selected: boolean; onPress: () => void }) {
  return (
    <Pressable
      onPress={onPress}
      accessibilityRole="button"
      accessibilityState={{ selected }}
      android_ripple={{ color: colors.brand100 }}
      style={{ minHeight: 56, paddingHorizontal: 16, paddingVertical: 10, flexDirection: "row", alignItems: "center", gap: 12, borderBottomWidth: 1, borderBottomColor: colors.border }}
    >
      <View style={{ flex: 1 }}>
        <Text numberOfLines={1} style={{ fontSize: 15, fontWeight: "600", color: selected ? colors.brand600 : colors.text }}>{title}</Text>
        {sub ? <Text numberOfLines={1} style={font.small}>{sub}</Text> : null}
      </View>
      {selected && <Ionicons name="checkmark" size={20} color={colors.brand600} />}
    </Pressable>
  );
}
