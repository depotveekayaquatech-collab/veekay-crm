import { useState } from "react";
import { Text, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import { useCashList } from "@/api/staffHooks";
import type { CashPurchase } from "@/api/staff";
import { useAuth } from "@/auth/AuthProvider";
import { Badge, Button, Card, Empty, ErrorNote, ListSkeleton, Pager, Screen } from "@/components/ui";
import { fmtDate } from "@/lib/format";
import { colors, font, radius } from "@/theme";

const money = (v: string | number) => `₹${Number(v).toLocaleString("en-IN", { maximumFractionDigits: 2 })}`;

export default function Cash() {
  const { hasPermission } = useAuth();
  const router = useRouter();
  const [page, setPage] = useState(1);
  const q = useCashList(page);

  // Group by date, newest first (like an expense app's feed).
  const groups = new Map<string, CashPurchase[]>();
  for (const p of q.data?.items ?? []) groups.set(p.purchase_date, [...(groups.get(p.purchase_date) ?? []), p]);

  return (
    <Screen onRefresh={() => q.refetch()} refreshing={q.isRefetching && !q.isLoading} padBottom={110}>
      <Card style={{ backgroundColor: colors.ink950, borderColor: colors.ink950 }}>
        <Text style={{ color: "rgba(255,255,255,0.65)", fontSize: 12 }}>Total of your cash purchases</Text>
        <Text style={{ color: colors.white, fontSize: 32, fontWeight: "800", marginTop: 2 }}>{q.data ? money(q.data.amount_total) : "–"}</Text>
        <Text style={{ color: "rgba(255,255,255,0.55)", fontSize: 12, marginTop: 2 }}>{q.data ? `${q.data.total} purchase${q.data.total === 1 ? "" : "s"}` : ""}</Text>
      </Card>

      {hasPermission("cash.add") && (
        <Button title="Add a purchase" onPress={() => router.push("/staff/expense/new")} icon={<Ionicons name="add-circle-outline" size={22} color="#fff" />} style={{ marginTop: 14 }} />
      )}

      <View style={{ marginTop: 18 }}>
        {q.isLoading ? <ListSkeleton /> : q.isError ? <ErrorNote message={q.error.message} onRetry={() => q.refetch()} /> : q.data!.items.length === 0 ? (
          <Empty title="No purchases yet" text="Cash you spend for the office or a store goes here, with a photo of the bill." />
        ) : (
          [...groups.entries()].map(([date, rows]) => (
            <View key={date} style={{ marginBottom: 14 }}>
              <Text style={[font.tiny, { fontWeight: "700", letterSpacing: 0.6, marginBottom: 6 }]}>{fmtDate(date).toUpperCase()}</Text>
              <Card style={{ padding: 0, overflow: "hidden" }}>
                {rows.map((p, i) => (
                  <View key={p.id} style={{ flexDirection: "row", alignItems: "center", gap: 12, padding: 14, borderTopWidth: i ? 1 : 0, borderTopColor: colors.border }}>
                    <View style={{ width: 40, height: 40, borderRadius: radius.md, backgroundColor: p.kind === "STORE" ? colors.brand50 : colors.warningSoft, alignItems: "center", justifyContent: "center" }}>
                      <Ionicons name={p.kind === "STORE" ? "storefront-outline" : "business-outline"} size={20} color={p.kind === "STORE" ? colors.brand600 : colors.warning} />
                    </View>
                    <View style={{ flex: 1 }}>
                      <Text numberOfLines={1} style={{ fontSize: 15, fontWeight: "700", color: colors.text }}>{p.category_label}{p.other_reason ? ` · ${p.other_reason}` : ""}</Text>
                      <Text numberOfLines={1} style={font.small}>{p.store_name ?? "Office"}</Text>
                    </View>
                    <View style={{ alignItems: "flex-end", gap: 4 }}>
                      <Text style={{ fontSize: 16, fontWeight: "800", color: colors.text }}>{money(p.amount)}</Text>
                      {p.has_proof ? <Badge tone="success">Bill attached</Badge> : null}
                    </View>
                  </View>
                ))}
              </Card>
            </View>
          ))
        )}
        {q.data && <Pager page={page} pageSize={q.data.page_size} total={q.data.total} onPage={setPage} />}
      </View>
    </Screen>
  );
}
