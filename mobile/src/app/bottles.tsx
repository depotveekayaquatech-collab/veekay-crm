import { useState } from "react";
import { Text, View } from "react-native";
import { useBottles } from "@/api/hooks";
import { Card, Empty, ErrorNote, ListSkeleton, Pager, Screen } from "@/components/ui";
import { StorePicker } from "@/components/StorePicker";
import { fmtDate } from "@/lib/format";
import { colors, font } from "@/theme";

export default function Bottles() {
  const [store, setStore] = useState("");
  const [page, setPage] = useState(1);
  const q = useBottles({ store_id: store || undefined, page, page_size: 50 });

  return (
    <Screen onRefresh={() => q.refetch()} refreshing={q.isRefetching && !q.isLoading}>
      <Text style={[font.small, { marginBottom: 14 }]}>Oldest first, so you can see which have been there longest.</Text>
      <StorePicker value={store} allLabel="All my stores" label="Showing" onChange={(v) => { setStore(v); setPage(1); }} />
      <View style={{ marginTop: 16 }}>
        {q.isLoading ? <ListSkeleton /> : q.isError ? <ErrorNote message={q.error.message} onRetry={() => q.refetch()} /> : q.data!.items.length === 0 ? (
          <Empty title="No bottles at your stores" text="Bottles show here after they are scanned in." />
        ) : (
          <>
            <Text style={{ fontWeight: "700", color: colors.text, marginBottom: 8 }}>{q.data!.total} bottle{q.data!.total === 1 ? "" : "s"}</Text>
            <View style={{ gap: 8 }}>
              {q.data!.items.map((b) => (
                <Card key={b.serial} style={{ flexDirection: "row", alignItems: "center", gap: 12, paddingVertical: 12 }}>
                  <View style={{ flex: 1 }}>
                    <Text style={{ fontFamily: "monospace", fontWeight: "700", color: colors.text }}>{b.serial}</Text>
                    <Text numberOfLines={1} style={font.small}>{b.store_name}</Text>
                  </View>
                  {b.last_in_at ? <Text style={font.tiny}>since {fmtDate(b.last_in_at)}</Text> : null}
                </Card>
              ))}
            </View>
          </>
        )}
        {q.data && <Pager page={page} pageSize={q.data.page_size} total={q.data.total} onPage={setPage} />}
      </View>
    </Screen>
  );
}
