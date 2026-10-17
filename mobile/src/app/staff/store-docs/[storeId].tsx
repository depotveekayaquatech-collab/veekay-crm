import { useState } from "react";
import { Text, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { Stack, useLocalSearchParams } from "expo-router";
import { useComplianceStore } from "@/api/complianceHooks";
import { AttachmentViewer, type ViewerSource } from "@/components/AttachmentViewer";
import { DocSlotCard } from "@/components/DocSlotCard";
import { DocUploadSheet } from "@/components/DocUploadSheet";
import { Badge, Card, Chips, Empty, ErrorNote, ListSkeleton, Screen } from "@/components/ui";
import { KINDS, monthLabel, STATUS_LABEL, STATUS_TONE, type DocKind } from "@/lib/compliance";
import { colors, font } from "@/theme";

/**
 * One store's documents for a month: the card, the invoice and the payment proof, each with its status, who uploaded it and when,
 * view, upload / replace, history and remove. The same records and rules as the web CRM's Compliance tab.
 */
export default function StoreDocs() {
  const p = useLocalSearchParams<{ storeId: string; code?: string; name?: string; month?: string; focus?: string }>();
  const focus: DocKind | undefined = p.focus === "card" || p.focus === "bill" || p.focus === "payment" ? p.focus : undefined;
  const [month, setMonth] = useState(p.month ?? "");
  const q = useComplianceStore(p.storeId, p.code ?? "", month || undefined);
  const [view, setView] = useState<ViewerSource | null>(null);
  const [sheet, setSheet] = useState<{ kind: DocKind; replacing: boolean } | null>(null);
  const row = q.row;
  const current = q.month || month;
  const kinds = focus ? [focus, ...KINDS.filter((k) => k !== focus)] : KINDS;

  return (
    <Screen onRefresh={() => void q.refetch()} refreshing={q.isRefetching && !q.isLoading}>
      <Stack.Screen options={{ title: p.name || row?.name || (focus === "card" ? "Store card" : "Compliance") }} />
      {q.months.length > 1 ? (
        <View style={{ marginBottom: 14 }}>
          <Chips options={q.months.map((m) => ({ value: m, label: monthLabel(m, false) }))} value={current} onChange={setMonth} />
        </View>
      ) : null}

      {q.isLoading ? <ListSkeleton rows={3} /> : q.isError ? <ErrorNote message={q.error.message} onRetry={() => void q.refetch()} /> : !row ? (
        <Empty icon="storefront-outline" title="This store isn't in your list for this month" text="It may not have started supplying yet, or it is not one of your stores." />
      ) : (
        <View style={{ gap: 14 }}>
          <Card style={{ gap: 6 }}>
            <View style={{ flexDirection: "row", alignItems: "center", gap: 10 }}>
              <View style={{ flex: 1 }}>
                <Text style={{ fontSize: 18, fontWeight: "800", color: colors.text }}>{row.name}</Text>
                <Text style={font.small}>
                  {row.external_code}{row.city ? ` · ${row.city}` : ""}{row.platform ? ` · ${row.platform}` : ""}
                </Text>
              </View>
              <Badge tone={STATUS_TONE[row.status]}>{row.percent}%</Badge>
            </View>
            <View style={{ flexDirection: "row", alignItems: "center", gap: 6 }}>
              <Ionicons name="calendar-outline" size={15} color={colors.textMuted} />
              <Text style={font.small}>{monthLabel(current)} · {STATUS_LABEL[row.status]}</Text>
            </View>
            {row.vendor_name ? <Text style={font.small}>Vendor: {row.vendor_name}</Text> : null}
          </Card>

          {kinds.map((kind) => (
            <DocSlotCard
              key={kind}
              kind={kind}
              doc={row[kind]}
              month={current}
              preview={kind === "card"}
              onView={setView}
              onUpload={(k, replacing) => setSheet({ kind: k, replacing })}
            />
          ))}
          <Text style={[font.tiny, { textAlign: "center" }]}>
            The same records as the web CRM: anything uploaded here appears there, and the other way round.
          </Text>
        </View>
      )}

      <AttachmentViewer source={view} onClose={() => setView(null)} />
      {sheet && row && current ? (
        <DocUploadSheet
          store={{ id: row.store_id, name: row.name, code: row.external_code }}
          month={current}
          kind={sheet.kind}
          replacing={sheet.replacing}
          onClose={() => setSheet(null)}
        />
      ) : null}
    </Screen>
  );
}

