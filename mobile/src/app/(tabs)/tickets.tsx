import { useState } from "react";
import { Text, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import { useAuth } from "@/auth/AuthProvider";
import { useTickets } from "@/api/hooks";
import { Button, Card, Chips, Empty, ErrorNote, ListSkeleton, Pager, Screen, TicketStatusBadge } from "@/components/ui";
import { fmtDateTime, titleCase } from "@/lib/format";
import { colors, font } from "@/theme";

const FILTERS = [
  { label: "All", value: "" },
  { label: "Open", value: "OPEN" },
  { label: "In progress", value: "IN_PROGRESS" },
  { label: "Resolved", value: "RESOLVED" },
];

export default function Tickets() {
  const { account } = useAuth();
  const router = useRouter();
  const isPoc = account?.kind === "poc";
  const [status, setStatus] = useState("");
  const [page, setPage] = useState(1);
  const q = useTickets({ status: status || undefined, page, page_size: 20 });

  return (
    <Screen onRefresh={() => q.refetch()} refreshing={q.isRefetching && !q.isLoading}>
      <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: 12, marginBottom: 14 }}>
        <Text style={[font.small, { flex: 1 }]}>{isPoc ? "Problems raised for your stores." : "Problems your store POCs have raised."}</Text>
        {isPoc && <Button title="New" onPress={() => router.push("/tickets/new")} icon={<Ionicons name="add" size={20} color="#fff" />} style={{ minHeight: 42, paddingHorizontal: 16 }} />}
      </View>
      <Chips options={FILTERS} value={status} onChange={(v) => { setStatus(v); setPage(1); }} />

      <View style={{ marginTop: 14 }}>
        {q.isLoading ? <ListSkeleton /> : q.isError ? <ErrorNote message={q.error.message} onRetry={() => q.refetch()} /> : q.data!.items.length === 0 ? (
          <Empty title="No tickets" text={isPoc ? "Raise one if something is wrong with a delivery." : "When a POC raises a ticket for your stores it appears here."} />
        ) : (
          <View style={{ gap: 10 }}>
            {q.data!.items.map((t) => (
              <Card key={t.id} onPress={() => router.push(`/tickets/${t.id}`)} label={`Ticket ${t.number}, ${t.title}`}>
                <View style={{ flexDirection: "row", alignItems: "flex-start", justifyContent: "space-between", gap: 10 }}>
                  <Text style={{ flex: 1, fontSize: 15, fontWeight: "700", color: colors.text }}>#{t.number} · {t.title}</Text>
                  <TicketStatusBadge status={t.status} />
                </View>
                <Text numberOfLines={1} style={[font.small, { marginTop: 6 }]}>{t.store_name} · {titleCase(t.category)} · {fmtDateTime(t.created_at)}</Text>
              </Card>
            ))}
          </View>
        )}
        {q.data && <Pager page={page} pageSize={q.data.page_size} total={q.data.total} onPage={setPage} />}
      </View>
    </Screen>
  );
}
