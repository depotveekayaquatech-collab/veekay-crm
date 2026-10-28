import { useMemo, useState } from "react";
import { FlatList, Linking, Modal, Pressable, ScrollView, Text, TextInput, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useAuth } from "@/auth/AuthProvider";
import { useAllCompliance } from "@/api/complianceHooks";
import { useMyStores } from "@/api/staffHooks";
import { Badge, Chips, Empty, ErrorNote, ListSkeleton } from "@/components/ui";
import { VendorPicker, vendorsOf } from "@/components/VendorPicker";
import { fmtMonth } from "@/lib/format";
import {
  chipCounts, groupByVendor, matchesSearch, passesFilter, pendingText, vendorKeyOf, type DocFlags, type InvFilter, type InvStore, type VendorGroup,
} from "@/lib/inventory";
import { colors, font, radius } from "@/theme";

const call = (number: string) => void Linking.openURL(`tel:${number.replace(/[^\d+]/g, "")}`).catch(() => undefined);

function Tile({ label, value, sub, warm }: { label: string; value: string; sub?: string; warm?: boolean }) {
  return (
    <View style={{ flexBasis: "47%", flexGrow: 1, backgroundColor: warm ? colors.warningSoft : colors.surface, borderRadius: radius.lg, borderWidth: 1, borderColor: colors.border, padding: 14, alignItems: "center" }}>
      <Text style={{ fontSize: 26, fontWeight: "800", color: warm ? colors.warning : colors.text }}>{value}</Text>
      <Text style={font.small}>{label}</Text>
      {sub ? <Text style={font.tiny}>{sub}</Text> : null}
    </View>
  );
}

function Phone({ number }: { number: string }) {
  return (
    <Pressable onPress={() => call(number)} accessibilityRole="link" accessibilityLabel={`Call ${number}`} hitSlop={6}>
      <Text style={{ color: colors.brand600, fontWeight: "700", fontSize: 13 }}>{number}</Text>
    </Pressable>
  );
}

function Count({ label, have, of }: { label: string; have: number | null; of: number }) {
  if (have === null) return null;
  const done = have >= of && of > 0;
  return (
    <View style={{ paddingHorizontal: 10, paddingVertical: 4, borderRadius: radius.pill, backgroundColor: done ? colors.successSoft : colors.surfaceMuted }}>
      <Text style={{ fontSize: 12, fontWeight: "800", color: done ? colors.success : colors.textMuted }}>{label} {have}/{of}</Text>
    </View>
  );
}

function VendorCard({ g, docsKnown, open, onToggle, onPick }: { g: VendorGroup; docsKnown: boolean; open: boolean; onToggle: () => void; onPick: (s: InvStore) => void }) {
  return (
    <View style={{ backgroundColor: colors.surface, borderRadius: radius.lg, borderWidth: 1, borderColor: colors.border, overflow: "hidden" }}>
      <Pressable onPress={onToggle} accessibilityRole="button" accessibilityState={{ expanded: open }} accessibilityLabel={`${g.name}, ${g.stores.length} stores`} android_ripple={{ color: colors.brand100 }}
        style={{ padding: 14, flexDirection: "row", alignItems: "center", gap: 12 }}>
        <View style={{ width: 40, height: 40, borderRadius: radius.md, backgroundColor: colors.brand50, alignItems: "center", justifyContent: "center" }}>
          <Text style={{ fontSize: 16, fontWeight: "800", color: colors.brand700 }}>{g.name.slice(0, 1).toUpperCase()}</Text>
        </View>
        <View style={{ flex: 1, gap: 2 }}>
          <Text numberOfLines={1} style={{ fontSize: 16, fontWeight: "800", color: colors.text }}>{g.name}</Text>
          <Text style={font.small}>{g.stores.length} store{g.stores.length === 1 ? "" : "s"}</Text>
        </View>
        <View style={{ alignItems: "flex-end", gap: 4 }}>
          <Count label="Cards" have={docsKnown ? g.cards : null} of={g.stores.length} />
          <Count label="Bills" have={docsKnown ? g.bills : null} of={g.stores.length} />
        </View>
        <Ionicons name={open ? "chevron-up" : "chevron-down"} size={16} color={colors.textFaint} />
      </Pressable>
      {g.phones.length > 0 && (
        <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 12, paddingHorizontal: 14, paddingBottom: open ? 8 : 12, marginTop: -4 }}>
          {g.phones.map((p) => <Phone key={p} number={p} />)}
        </View>
      )}
      {open && (
        <View>
          {g.stores.map((s) => (
            <Pressable key={s.id} onPress={() => onPick(s)} accessibilityRole="button" accessibilityLabel={`${s.name}, ${pendingText(s.pending_days)}`} android_ripple={{ color: colors.brand100 }}
              style={{ paddingHorizontal: 14, paddingVertical: 12, borderTopWidth: 1, borderTopColor: colors.border, flexDirection: "row", alignItems: "center", gap: 10 }}>
              <View style={{ flex: 1 }}>
                <Text numberOfLines={2} style={{ fontSize: 15, fontWeight: "600", color: colors.text }}>{s.name}</Text>
                <Text numberOfLines={1} style={font.small}>{s.external_code}{s.city ? ` · ${s.city}` : ""}</Text>
              </View>
              {(s.pending_days ?? 0) > 0 ? <Badge tone="warning">{pendingText(s.pending_days)}</Badge> : null}
              <Ionicons name="chevron-forward" size={16} color={colors.textFaint} />
            </Pressable>
          ))}
        </View>
      )}
    </View>
  );
}

function Field({ label, value, phone }: { label: string; value: string | null | undefined; phone?: boolean }) {
  return (
    <View style={{ flexBasis: "47%", flexGrow: 1, gap: 2 }}>
      <Text style={font.small}>{label}</Text>
      {value ? (phone ? <Phone number={value} /> : <Text style={{ fontSize: 15, fontWeight: "700", color: colors.text }}>{value}</Text>) : <Text style={{ fontSize: 15, color: colors.textFaint }}>—</Text>}
    </View>
  );
}

/** One store's details: where it is, how far behind, who to call (the POC and the vendor), and the shortcuts to mark it or open its documents. */
function StoreSheet({ s, docs, onClose, canMark, canDocs }: { s: InvStore | null; docs: DocFlags | undefined; onClose: () => void; canMark: boolean; canDocs: boolean }) {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  if (!s) return null;
  const behind = (s.pending_days ?? 0) > 0;
  const go = (to: string) => { onClose(); router.push(to as never); };
  return (
    <Modal visible transparent animationType="slide" onRequestClose={onClose}>
      <Pressable style={{ flex: 1, backgroundColor: "rgba(0,0,0,0.4)" }} onPress={onClose} accessibilityLabel="Close" />
      <View style={{ maxHeight: "85%", backgroundColor: colors.surface, borderTopLeftRadius: radius.xl, borderTopRightRadius: radius.xl, paddingBottom: insets.bottom + 12 }}>
        <ScrollView contentContainerStyle={{ padding: 18, gap: 14 }}>
          <View style={{ flexDirection: "row", alignItems: "flex-start", justifyContent: "space-between", gap: 10 }}>
            <View style={{ flex: 1 }}>
              <Text style={font.small}>Selected store</Text>
              <Text style={{ fontSize: 20, fontWeight: "800", color: colors.text }}>{s.name}</Text>
            </View>
            <Pressable onPress={onClose} hitSlop={10} accessibilityRole="button" accessibilityLabel="Close"><Ionicons name="close" size={24} color={colors.textMuted} /></Pressable>
          </View>
          <View style={{ padding: 12, borderRadius: radius.md, backgroundColor: behind ? colors.warningSoft : colors.successSoft }}>
            <Text style={{ fontWeight: "800", color: behind ? colors.warning : colors.success }}>{pendingText(s.pending_days)}</Text>
          </View>
          {docs && (
            <View style={{ flexDirection: "row", gap: 8 }}>
              <Badge tone={docs.card ? "success" : "warning"}>{docs.card ? "Card ✓" : "Card missing"}</Badge>
              <Badge tone={docs.bill ? "success" : "warning"}>{docs.bill ? "Bill ✓" : "Bill missing"}</Badge>
            </View>
          )}
          <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 16 }}>
            <Field label="Outlet ID" value={s.external_code} />
            <Field label="City" value={s.city} />
            <Field label="State" value={s.state} />
            <Field label="Region" value={s.region_name} />
            <Field label="POC name" value={s.poc_name} />
            <Field label="POC number" value={s.poc_number} phone />
            <Field label="Vendor name" value={s.vendor_name} />
            <Field label="Vendor number" value={s.vendor_number} phone />
          </View>
          <View style={{ flexDirection: "row", gap: 10 }}>
            {canMark && (
              <Pressable onPress={() => go(`/staff/mark/${s.id}`)} accessibilityRole="button" style={{ flex: 1, minHeight: 46, borderRadius: radius.md, backgroundColor: colors.brand600, alignItems: "center", justifyContent: "center" }}>
                <Text style={{ color: colors.white, fontWeight: "800" }}>Mark orders</Text>
              </Pressable>
            )}
            {canDocs && (
              <Pressable onPress={() => go(`/staff/store-docs/${s.id}`)} accessibilityRole="button" style={{ flex: 1, minHeight: 46, borderRadius: radius.md, backgroundColor: colors.brand50, alignItems: "center", justifyContent: "center" }}>
                <Text style={{ color: colors.brand600, fontWeight: "800" }}>Documents</Text>
              </Pressable>
            )}
          </View>
        </ScrollView>
      </View>
    </Modal>
  );
}

/**
 * Inventory: every live store assigned to you, grouped by vendor. Each vendor shows its phone numbers and how many of its stores have this month's card and
 * bill; tap a vendor to open its stores and a store to see its POC and vendor details. All of it is read from the same server data as the rest of the app.
 */
export default function Inventory() {
  const { hasPermission } = useAuth();
  const canDocs = hasPermission("compliance.upload") || hasPermission("compliance.manage");
  const canMark = hasPermission("orders.mark");
  const stores = useMyStores();
  const [month, setMonth] = useState("");                       // "" = the server's month
  const docsQ = useAllCompliance(month, canDocs);
  const [needle, setNeedle] = useState("");
  const [vendor, setVendor] = useState("");
  const [filter, setFilter] = useState<InvFilter>("all");
  const [openKey, setOpenKey] = useState<string | null>(null);
  const [picked, setPicked] = useState<InvStore | null>(null);

  const live = useMemo(() => (stores.data ?? []).filter((s) => s.status === "LIVE") as InvStore[], [stores.data]);
  const docs = useMemo(() => {
    const m = new Map<string, DocFlags>();
    for (const r of docsQ.data?.items ?? []) m.set(r.store_id, { card: !!r.card, bill: !!r.bill });
    return m;
  }, [docsQ.data]);
  const docsKnown = canDocs && !!docsQ.data;

  const vendors = useMemo(() => vendorsOf(live), [live]);
  const scope = useMemo(() => live.filter((s) => (!vendor || vendorKeyOf(s.vendor_name) === vendor) && matchesSearch(s, needle)), [live, vendor, needle]);
  const counts = useMemo(() => chipCounts(scope, docs), [scope, docs]);
  const shown = useMemo(() => scope.filter((s) => passesFilter(s, docs, filter)), [scope, docs, filter]);
  const groups = useMemo(() => groupByVendor(shown, docs), [shown, docs]);
  const autoOpen = groups.length <= 2 || needle.trim() !== "";

  const cards = live.filter((s) => docs.get(s.id)?.card).length;
  const bills = live.filter((s) => docs.get(s.id)?.bill).length;
  const monthValue = docsQ.data?.month ?? month;
  const refetch = () => { void stores.refetch(); if (canDocs) void docsQ.refetch(); };

  const chips: { label: string; value: InvFilter }[] = [
    { label: `All ${counts.all}`, value: "all" },
    ...(docsKnown ? [{ label: `Card missing ${counts.card}`, value: "card" as const }, { label: `Bill missing ${counts.bill}`, value: "bill" as const }] : []),
    { label: `Orders pending ${counts.orders}`, value: "orders" },
  ];

  const header = (
    <View style={{ gap: 12, marginBottom: 4 }}>
      <Text style={font.small}>Every store assigned to you, grouped by vendor. Tap a store to see its POC and vendor details.</Text>
      <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 10 }}>
        <Tile label="Stores" value={String(live.length)} />
        <Tile label="Vendors" value={String(vendors.length)} />
        {docsKnown && <Tile warm label="Cards" value={`${cards}/${live.length}`} sub={docsQ.data?.month_label} />}
        {docsKnown && <Tile warm label="Bills" value={`${bills}/${live.length}`} sub={docsQ.data?.month_label} />}
      </View>
      <View style={{ flexDirection: "row", alignItems: "center", gap: 8, height: 48, borderRadius: radius.md, backgroundColor: colors.surface, borderWidth: 1.5, borderColor: colors.border, paddingHorizontal: 12 }}>
        <Ionicons name="search" size={18} color={colors.textFaint} />
        <TextInput value={needle} onChangeText={setNeedle} placeholder="Store, outlet ID or city" placeholderTextColor={colors.textFaint} accessibilityLabel="Search" style={{ flex: 1, fontSize: 16, color: colors.text }} />
      </View>
      <VendorPicker vendors={vendors} value={vendor} onChange={(k) => { setVendor(k); setOpenKey(null); }} />
      {docsKnown && docsQ.data && docsQ.data.months.length > 1 && (
        <View style={{ gap: 6 }}>
          <Text style={font.small}>Documents for</Text>
          <Chips options={docsQ.data.months.slice(0, 6).map((m) => ({ label: fmtMonth(`${m}-01`), value: m }))} value={monthValue} onChange={setMonth} />
        </View>
      )}
      <Chips<InvFilter> options={chips} value={filter} onChange={setFilter} />
    </View>
  );

  return (
    <View style={{ flex: 1, backgroundColor: colors.surfaceSubtle }}>
      <FlatList
        data={groups}
        keyExtractor={(g) => g.key || "none"}
        keyboardShouldPersistTaps="handled"
        onRefresh={refetch}
        refreshing={(stores.isRefetching || docsQ.isRefetching) && !stores.isLoading}
        contentContainerStyle={{ padding: 16, paddingBottom: 40, gap: 10 }}
        ListHeaderComponent={header}
        ListEmptyComponent={
          stores.isLoading ? <ListSkeleton />
          : stores.isError ? <ErrorNote message={stores.error.message} onRetry={refetch} />
          : live.length === 0 ? <Empty icon="storefront-outline" title="No stores assigned yet" text="Ask your admin to assign you a region or states." />
          : <Empty title="No stores match" text="Try another search or filter." />
        }
        renderItem={({ item }) => (
          <VendorCard g={item} docsKnown={docsKnown} open={autoOpen || openKey === item.key} onToggle={() => setOpenKey(openKey === item.key ? null : item.key)} onPick={setPicked} />
        )}
      />
      <StoreSheet s={picked} docs={picked ? docs.get(picked.id) : undefined} onClose={() => setPicked(null)} canMark={canMark} canDocs={canDocs} />
    </View>
  );
}
