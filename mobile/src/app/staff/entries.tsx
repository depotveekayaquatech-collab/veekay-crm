import { useMemo, useState } from "react";
import { FlatList, Text, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useMyEntries } from "@/api/staffHooks";
import type { MyEntry } from "@/api/staff";
import { Chips, Empty, ErrorNote, ListSkeleton } from "@/components/ui";
import { fmtNumber } from "@/lib/format";
import { colors, font, radius } from "@/theme";

type Range = "3" | "7" | "14";
type Row = { kind: "day"; date: string; stores: number; bottles: number } | { kind: "entry"; entry: MyEntry };

const dayTitle = (iso: string) => new Date(`${iso}T00:00:00`).toLocaleDateString("en-IN", { weekday: "long", day: "numeric", month: "short" });

/** Everything this person entered in the last few days, day by day: a way to check that an entry was saved, whatever its store is today. */
export default function MyEntries() {
  const [range, setRange] = useState<Range>("7");
  const q = useMyEntries(Number(range));

  const rows = useMemo<Row[]>(() => {
    const out: Row[] = [];
    const items = q.data?.items ?? [];
    for (let i = 0; i < items.length; ) {
      const date = items[i].order_date;
      let j = i;
      let bottles = 0;
      while (j < items.length && items[j].order_date === date) bottles += items[j++].bottles;
      out.push({ kind: "day", date, stores: j - i, bottles });
      for (let k = i; k < j; k++) out.push({ kind: "entry", entry: items[k] });
      i = j;
    }
    return out;
  }, [q.data]);

  return (
    <View style={{ flex: 1, backgroundColor: colors.surfaceSubtle }}>
      <FlatList
        data={rows}
        keyExtractor={(r, i) => (r.kind === "day" ? `d-${r.date}` : `e-${r.entry.store_id}-${r.entry.order_date}-${i}`)}
        onRefresh={() => q.refetch()}
        refreshing={q.isRefetching && !q.isLoading}
        contentContainerStyle={{ padding: 16, paddingBottom: 40, gap: 8 }}
        ListHeaderComponent={
          <View style={{ gap: 10, marginBottom: 6 }}>
            <Chips<Range> options={[{ label: "Last 3 days", value: "3" }, { label: "Last 7 days", value: "7" }, { label: "Last 14 days", value: "14" }]} value={range} onChange={setRange} />
            <Text style={font.small}>
              {q.data ? `${fmtNumber(q.data.total)} entr${q.data.total === 1 ? "y" : "ies"} saved under your name.` : "Loading…"} A store that is no longer live still shows here.
            </Text>
          </View>
        }
        ListEmptyComponent={q.isLoading ? <ListSkeleton /> : q.isError ? <ErrorNote message={q.error.message} onRetry={() => q.refetch()} /> : <Empty title="No entries in this period" text="Entries you mark appear here as soon as they are saved." />}
        renderItem={({ item }) =>
          item.kind === "day" ? (
            <View style={{ marginTop: 10, flexDirection: "row", alignItems: "baseline", justifyContent: "space-between", gap: 8 }}>
              <Text style={{ fontSize: 15, fontWeight: "800", color: colors.text }}>{dayTitle(item.date)}</Text>
              <Text style={font.small}>{item.stores} store{item.stores === 1 ? "" : "s"} · {fmtNumber(item.bottles)} bottles</Text>
            </View>
          ) : (
            <View style={{ backgroundColor: colors.surface, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, paddingVertical: 10, paddingHorizontal: 12, flexDirection: "row", alignItems: "center", gap: 10 }}>
              <View style={{ flex: 1 }}>
                <Text numberOfLines={2} style={{ fontSize: 14, fontWeight: "700", color: colors.text }}>{item.entry.store_name}</Text>
                <Text numberOfLines={1} style={font.tiny}>{item.entry.store_code}{item.entry.city ? ` · ${item.entry.city}` : ""}</Text>
                <Text style={{ fontSize: 11, fontWeight: "700", color: colors.success, marginTop: 2 }}>
                  <Ionicons name="cloud-done-outline" size={12} color={colors.success} /> Saved on the server{item.entry.corrected ? " · corrected by your Team Lead or an admin" : ""}
                </Text>
                {item.entry.store_status !== "LIVE" ? (
                  <View style={{ alignSelf: "flex-start", marginTop: 4, flexDirection: "row", alignItems: "center", gap: 4, paddingHorizontal: 8, paddingVertical: 2, borderRadius: radius.pill, backgroundColor: colors.warningSoft }}>
                    <Ionicons name="information-circle-outline" size={13} color={colors.warning} />
                    <Text style={{ fontSize: 11, fontWeight: "700", color: colors.warning }}>Store is {item.entry.store_status.toLowerCase()} now</Text>
                  </View>
                ) : null}
              </View>
              <Text style={{ fontSize: 18, fontWeight: "800", color: colors.text }}>{item.entry.bottles}</Text>
            </View>
          )
        }
      />
    </View>
  );
}
