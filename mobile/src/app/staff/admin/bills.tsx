import { Text, View } from "react-native";
import { useDueBills } from "@/api/adminHooks";
import { Badge, Card, Empty, ErrorNote, ListSkeleton, Screen } from "@/components/ui";
import { fmtDate, fmtMonth } from "@/lib/format";
import { colors, font } from "@/theme";

/** Pending bills whose due date has arrived, most overdue first. */
export default function BillsDue() {
  const q = useDueBills();
  return (
    <Screen onRefresh={() => q.refetch()} refreshing={q.isRefetching && !q.isLoading}>
      <Text style={[font.small, { marginBottom: 12 }]}>{q.data ? `${q.data.total} bill${q.data.total === 1 ? "" : "s"} past the due date and not yet cleared.` : "Bills past their due date."}</Text>
      <View style={{ gap: 10 }}>
        {q.isLoading ? <ListSkeleton /> : q.isError ? <ErrorNote message={q.error.message} onRetry={() => q.refetch()} /> : q.data!.items.length === 0 ? (
          <Empty title="No bills past due" text="Every due bill has been cleared." />
        ) : q.data!.items.map((b) => (
          <Card key={b.id}>
            <View style={{ flexDirection: "row", alignItems: "flex-start", justifyContent: "space-between", gap: 10 }}>
              <Text style={{ flex: 1, fontSize: 15, fontWeight: "700", color: colors.text }}>{b.store_name}</Text>
              <Badge tone={b.days_overdue > 15 ? "danger" : "warning"}>{b.days_overdue} days late</Badge>
            </View>
            <Text numberOfLines={1} style={[font.small, { marginTop: 4 }]}>{b.external_code}{b.platform ? ` · ${b.platform}` : ""}{b.state ? ` · ${b.state}` : ""}</Text>
            <Text style={{ marginTop: 6, color: colors.text }}>{fmtMonth(b.month)} bill · due {fmtDate(b.due_date)}</Text>
            {b.vendor_name ? <Text style={font.small}>Vendor: {b.vendor_name}</Text> : null}
          </Card>
        ))}
      </View>
    </Screen>
  );
}
