import { useState } from "react";
import { Text, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import { useAuth } from "@/auth/AuthProvider";
import { useDeliveries } from "@/api/hooks";
import { Button, Card, Empty, ErrorNote, ListSkeleton, OutcomeBadge, Pager, Screen } from "@/components/ui";
import { fmtDate } from "@/lib/format";
import { colors, font } from "@/theme";

export default function Deliveries() {
  const { account } = useAuth();
  const router = useRouter();
  const isPoc = account?.kind === "poc";
  const [page, setPage] = useState(1);
  const q = useDeliveries({ page, page_size: 30 });

  return (
    <Screen onRefresh={() => q.refetch()} refreshing={q.isRefetching && !q.isLoading}>
      <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: 12, marginBottom: 14 }}>
        <Text style={[font.small, { flex: 1 }]}>{isPoc ? "Confirmed or reported at your stores." : "What your store POCs have confirmed or reported."}</Text>
        {isPoc && <Button title="Confirm" onPress={() => router.push("/deliveries/new")} icon={<Ionicons name="add" size={20} color="#fff" />} style={{ minHeight: 42, paddingHorizontal: 16 }} />}
      </View>
      {q.isLoading ? <ListSkeleton /> : q.isError ? <ErrorNote message={q.error.message} onRetry={() => q.refetch()} /> : q.data!.items.length === 0 ? (
        <Empty title="Nothing confirmed yet" text={isPoc ? "Confirm a delivery, or flag one that came short or damaged." : "Deliveries your POCs confirm or flag will show here."} />
      ) : (
        <View style={{ gap: 10 }}>
          {q.data!.items.map((d) => (
            <Card key={d.id}>
              <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: 10 }}>
                <Text style={{ fontSize: 15, fontWeight: "700", color: colors.text }}>{fmtDate(d.delivery_date)}</Text>
                <OutcomeBadge outcome={d.outcome} />
              </View>
              <Text numberOfLines={1} style={[font.small, { marginTop: 4 }]}>{d.store_name} · {d.reported_by}</Text>
              {d.expected_qty !== null && d.received_qty !== null ? <Text style={{ marginTop: 6, color: colors.text }}>Expected {d.expected_qty}, received {d.received_qty}</Text> : null}
              {d.note ? <Text style={{ marginTop: 6, color: colors.text, lineHeight: 20 }}>{d.note}</Text> : null}
              {d.ticket_id ? <Text onPress={() => router.push(`/tickets/${d.ticket_id}`)} accessibilityRole="link" style={{ marginTop: 10, color: colors.brand600, fontWeight: "700" }}>View ticket</Text> : null}
            </Card>
          ))}
        </View>
      )}
      {q.data && <Pager page={page} pageSize={q.data.page_size} total={q.data.total} onPage={setPage} />}
    </Screen>
  );
}
