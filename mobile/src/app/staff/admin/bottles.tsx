import { useState } from "react";
import { Text, View } from "react-native";
import { useBottleSummary, useOverdue } from "@/api/adminHooks";
import { Badge, Card, Empty, ErrorNote, ListSkeleton, Pager, Screen } from "@/components/ui";
import { fmtDate, fmtNumber } from "@/lib/format";
import { colors, font } from "@/theme";

/** Bottles whose last scan was IN and that have sat at a store longer than the lost-after limit, oldest first. */
export default function OverdueBottles() {
  const [page, setPage] = useState(1);
  const sum = useBottleSummary(true);
  const q = useOverdue(page);

  return (
    <Screen onRefresh={() => { void sum.refetch(); void q.refetch(); }} refreshing={q.isRefetching && !q.isLoading}>
      {sum.data && (
        <View style={{ flexDirection: "row", gap: 10 }}>
          {[
            { label: "At stores", value: sum.data.at_store, color: colors.text },
            { label: "Overdue", value: sum.data.overdue, color: sum.data.overdue ? colors.danger : colors.success },
            { label: "In circulation", value: sum.data.total_active, color: colors.text },
          ].map((s) => (
            <Card key={s.label} style={{ flex: 1, padding: 12, alignItems: "center" }}>
              <Text style={{ fontSize: 22, fontWeight: "800", color: s.color }}>{fmtNumber(s.value)}</Text>
              <Text style={font.tiny}>{s.label}</Text>
            </Card>
          ))}
        </View>
      )}
      {sum.data && <Text style={[font.small, { marginTop: 10 }]}>Overdue means at a store for more than {sum.data.lost_after_days} days without being scanned out.</Text>}

      <View style={{ marginTop: 14, gap: 8 }}>
        {q.isLoading ? <ListSkeleton /> : q.isError ? <ErrorNote message={q.error.message} onRetry={() => q.refetch()} /> : q.data!.items.length === 0 ? (
          <Empty title="No overdue bottles" text="Every bottle at a store has been scanned recently." />
        ) : q.data!.items.map((b) => (
          <Card key={b.serial} style={{ flexDirection: "row", alignItems: "center", gap: 12, paddingVertical: 12 }}>
            <View style={{ flex: 1 }}>
              <Text style={{ fontFamily: "monospace", fontWeight: "800", color: colors.text }}>{b.serial}</Text>
              <Text numberOfLines={1} style={font.small}>{b.store_name ?? "Unknown store"}{b.last_in_at ? ` · in since ${fmtDate(b.last_in_at)}` : ""}</Text>
            </View>
            {b.days_at_store !== null ? <Badge tone="danger">{b.days_at_store} days</Badge> : null}
          </Card>
        ))}
        {q.data && <Pager page={page} pageSize={q.data.page_size} total={q.data.total} onPage={setPage} />}
      </View>
    </Screen>
  );
}
