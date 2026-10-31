import { useState } from "react";
import { Pressable, Text, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useDailyOrders, useOrders } from "@/api/hooks";
import { Card, Chips, Empty, ErrorNote, IconTile, ListSkeleton, Screen } from "@/components/ui";
import { StorePicker } from "@/components/StorePicker";
import { daysAgo, fmtDate, fmtNumber } from "@/lib/format";
import { colors, font, radius } from "@/theme";

const RANGES = [
  { label: "7 days", value: "6" },
  { label: "31 days", value: "30" },
  { label: "3 months", value: "90" },
];

/** The stores behind one day's total; fetched only once the day is opened. */
function DayStores({ day, store }: { day: string; store: string }) {
  const q = useOrders({ store_id: store || undefined, date_from: day, date_to: day, page_size: 200 });
  if (q.isLoading) return <Text style={[font.small, { padding: 14 }]}>Loading…</Text>;
  if (q.isError) return <View style={{ padding: 12 }}><ErrorNote message={q.error.message} onRetry={() => q.refetch()} /></View>;
  return (
    <View style={{ backgroundColor: colors.surfaceSubtle, borderTopWidth: 1, borderTopColor: colors.border }}>
      {q.data!.items.map((r) => (
        <View key={r.store_id} style={{ flexDirection: "row", justifyContent: "space-between", gap: 12, paddingHorizontal: 16, paddingVertical: 10 }}>
          <Text numberOfLines={1} style={{ flex: 1, color: colors.text }}>{r.store_name}</Text>
          <Text style={{ fontWeight: "700", color: colors.text }}>{r.bottle_count}</Text>
        </View>
      ))}
    </View>
  );
}

export default function Orders() {
  const params = useLocalSearchParams<{ store?: string }>();
  const router = useRouter();
  const store = params.store ?? "";
  const [days, setDays] = useState("30");
  const [open, setOpen] = useState<string | null>(null);
  const q = useDailyOrders({ store_id: store || undefined, date_from: daysAgo(Number(days)), date_to: daysAgo(0) });

  const total = q.data?.reduce((n, d) => n + d.bottles, 0) ?? 0;
  const best = q.data?.reduce((m, d) => Math.max(m, d.bottles), 0) ?? 0;

  return (
    <Screen onRefresh={() => q.refetch()} refreshing={q.isRefetching && !q.isLoading}>
      <Text style={[font.small, { marginBottom: 14 }]}>Bottles delivered each day. Tap a day to see the stores.</Text>
      <View style={{ gap: 12 }}>
        <StorePicker value={store} allLabel="All my stores" label="Showing" onChange={(v) => { router.setParams({ store: v || undefined }); setOpen(null); }} />
        <Chips options={RANGES} value={days} onChange={(v) => { setDays(v); setOpen(null); }} />
      </View>

      {q.data && q.data.length > 0 && (
        <View style={{ flexDirection: "row", gap: 12, marginTop: 16 }}>
          <Card style={{ flex: 1, gap: 12 }}>
            <IconTile icon="cube-outline" bg={colors.brand50} fg={colors.brand600} size={38} />
            <View>
              <Text style={{ fontSize: 26, fontWeight: "800", color: colors.text }}>{fmtNumber(total)}</Text>
              <Text style={font.small}>Total bottles</Text>
            </View>
          </Card>
          <Card style={{ flex: 1, gap: 12 }}>
            <IconTile icon="analytics-outline" bg={colors.aquaSoft} fg={colors.aqua700} size={38} />
            <View>
              <Text style={{ fontSize: 26, fontWeight: "800", color: colors.text }}>{fmtNumber(Math.round(total / q.data.length))}</Text>
              <Text style={font.small}>Daily average</Text>
            </View>
          </Card>
        </View>
      )}

      <View style={{ marginTop: 16 }}>
        {q.isLoading ? <ListSkeleton /> : q.isError ? <ErrorNote message={q.error.message} onRetry={() => q.refetch()} /> : q.data!.length === 0 ? (
          <Empty title="No orders in this period" text="Daily counts appear here once stores are marked." />
        ) : (
          <Card style={{ padding: 0, overflow: "hidden" }}>
            {q.data!.map((d, i) => {
              const isOpen = open === d.order_date;
              return (
                <View key={d.order_date} style={{ borderTopWidth: i ? 1 : 0, borderTopColor: colors.border }}>
                  <Pressable
                    onPress={() => setOpen(isOpen ? null : d.order_date)}
                    accessibilityRole="button"
                    accessibilityState={{ expanded: isOpen }}
                    accessibilityLabel={`${fmtDate(d.order_date)}, ${d.bottles} bottles, ${d.stores} stores`}
                    android_ripple={{ color: colors.brand100 }}
                    style={({ pressed }) => ({ minHeight: 64, paddingHorizontal: 16, paddingVertical: 12, flexDirection: "row", alignItems: "center", gap: 12, backgroundColor: pressed ? colors.surfaceSubtle : "transparent" })}
                  >
                    <View style={{ flex: 1 }}>
                      <Text style={{ fontSize: 15, fontWeight: "600", color: colors.text }}>{fmtDate(d.order_date)}</Text>
                      <View style={{ height: 6, borderRadius: radius.pill, backgroundColor: colors.surfaceMuted, marginTop: 8, overflow: "hidden" }}>
                        <View style={{ height: 6, borderRadius: radius.pill, backgroundColor: colors.brand500, width: `${best ? (d.bottles / best) * 100 : 0}%` }} />
                      </View>
                    </View>
                    <View style={{ width: 76, alignItems: "flex-end" }}>
                      <Text style={{ fontSize: 17, fontWeight: "800", color: colors.text }}>{fmtNumber(d.bottles)}</Text>
                      <Text style={font.tiny}>{d.stores} store{d.stores === 1 ? "" : "s"}</Text>
                    </View>
                    <Ionicons name={isOpen ? "chevron-up" : "chevron-down"} size={18} color={colors.textFaint} />
                  </Pressable>
                  {isOpen && <DayStores day={d.order_date} store={store} />}
                </View>
              );
            })}
          </Card>
        )}
      </View>
    </Screen>
  );
}
