import { useMemo, useState } from "react";
import { FlatList, Modal, Pressable, Text, TextInput, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { colors, font, radius } from "@/theme";

export interface VendorOption { key: string; name: string; stores: number }

/** The distinct vendors in a list of stores (same vendor spelled with different case or spacing counts once), A to Z. */
export function vendorsOf(stores: { vendor_name: string | null }[]): VendorOption[] {
  const found = new Map<string, VendorOption>();
  for (const s of stores) {
    const name = s.vendor_name?.trim().replace(/\s+/g, " ");
    if (!name) continue;
    const key = name.toLowerCase();
    const have = found.get(key);
    if (have) have.stores += 1;
    else found.set(key, { key, name, stores: 1 });
  }
  return [...found.values()].sort((a, b) => a.name.localeCompare(b.name));
}

export const vendorKey = (name: string | null | undefined) => (name ?? "").trim().replace(/\s+/g, " ").toLowerCase();

/** "Vendor" field that opens a searchable list of vendors; picking one narrows the store list to that vendor's stores. */
export function VendorPicker({ vendors, value, onChange }: { vendors: VendorOption[]; value: string; onChange: (key: string) => void }) {
  const insets = useSafeAreaInsets();
  const [open, setOpen] = useState(false);
  const [needle, setNeedle] = useState("");
  const current = vendors.find((v) => v.key === value);
  const shown = useMemo(() => {
    const n = needle.trim().toLowerCase();
    return vendors.filter((v) => !n || v.key.includes(n));
  }, [vendors, needle]);

  const close = () => { setOpen(false); setNeedle(""); };
  const pick = (key: string) => { onChange(key); close(); };

  return (
    <View>
      <View style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
        <Pressable
          onPress={() => setOpen(true)}
          accessibilityRole="button"
          accessibilityLabel={`Vendor: ${current ? current.name : "all vendors"}. Double tap to change.`}
          style={{ flex: 1, minHeight: 48, borderRadius: radius.md, borderWidth: 1.5, borderColor: current ? colors.brand500 : colors.border, backgroundColor: current ? colors.brand50 : colors.surface, paddingHorizontal: 12, flexDirection: "row", alignItems: "center", gap: 8 }}
        >
          <Ionicons name="business-outline" size={18} color={current ? colors.brand600 : colors.textFaint} />
          <Text numberOfLines={1} style={{ flex: 1, fontSize: 16, color: current ? colors.brand700 : colors.textFaint, fontWeight: current ? "700" : "400" }}>
            {current ? `${current.name} · ${current.stores} store${current.stores === 1 ? "" : "s"}` : "Filter by vendor"}
          </Text>
          <Ionicons name="chevron-down" size={18} color={colors.textFaint} />
        </Pressable>
        {current ? (
          <Pressable onPress={() => onChange("")} accessibilityRole="button" accessibilityLabel="Clear the vendor filter" hitSlop={6}
            style={{ width: 48, height: 48, borderRadius: radius.md, alignItems: "center", justifyContent: "center", backgroundColor: colors.surface, borderWidth: 1.5, borderColor: colors.border }}>
            <Ionicons name="close" size={20} color={colors.text} />
          </Pressable>
        ) : null}
      </View>

      <Modal visible={open} animationType="slide" onRequestClose={close} statusBarTranslucent>
        <View style={{ flex: 1, backgroundColor: colors.surface, paddingTop: insets.top }}>
          <View style={{ flexDirection: "row", alignItems: "center", gap: 8, padding: 12, borderBottomWidth: 1, borderBottomColor: colors.border }}>
            <View style={{ flex: 1, flexDirection: "row", alignItems: "center", gap: 8, height: 46, borderRadius: radius.md, backgroundColor: colors.surfaceSubtle, paddingHorizontal: 12 }}>
              <Ionicons name="search" size={18} color={colors.textFaint} />
              <TextInput
                autoFocus
                value={needle}
                onChangeText={setNeedle}
                placeholder="Search vendor name"
                placeholderTextColor={colors.textFaint}
                accessibilityLabel="Search vendors"
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
            keyExtractor={(v) => v.key}
            keyboardShouldPersistTaps="handled"
            contentContainerStyle={{ paddingBottom: insets.bottom }}
            ListHeaderComponent={!needle.trim() ? <Row title="All vendors" selected={value === ""} onPress={() => pick("")} /> : null}
            ListEmptyComponent={<Text style={[font.small, { textAlign: "center", padding: 40 }]}>No vendor matches “{needle}”.</Text>}
            renderItem={({ item }) => (
              <Row title={item.name} sub={`${item.stores} store${item.stores === 1 ? "" : "s"}`} selected={item.key === value} onPress={() => pick(item.key)} />
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
