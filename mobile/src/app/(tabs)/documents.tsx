import { useEffect, useState } from "react";
import { Alert, Pressable, Text, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useDocuments } from "@/api/hooks";
import type { DocumentRow } from "@/api/api";
import { Badge, Button, Card, Chips, Empty, ErrorNote, IconTile, ListSkeleton, Pager, Screen } from "@/components/ui";
import { StorePicker } from "@/components/StorePicker";
import { openRemoteFile } from "@/lib/files";
import { daysAgo, fmtDate, fmtMonth, fmtSize } from "@/lib/format";
import { colors, font, radius } from "@/theme";

const KINDS = [
  { label: "All", value: "" },
  { label: "Cards", value: "card" },
  { label: "Bills", value: "bill" },
  { label: "Payments", value: "payment" },
];
const KIND_NAME = { card: "Compliance card", bill: "Bill", payment: "Payment proof" } as const;
const KIND_ICON = { card: "id-card-outline", bill: "receipt-outline", payment: "card-outline" } as const;

function BillState({ d }: { d: DocumentRow }) {
  if (d.kind !== "bill" || !d.status) return null;
  if (d.status === "CLEARED") return <Badge tone="success">Cleared</Badge>;
  const late = d.due_date && d.due_date <= daysAgo(0);
  return <Badge tone={late ? "danger" : "warning"}>{late ? "Overdue" : "Due"} {d.due_date ? fmtDate(d.due_date) : ""}</Badge>;
}

export default function Documents() {
  const router = useRouter();
  const params = useLocalSearchParams<{ kind?: string }>();
  const [kind, setKind] = useState(params.kind ?? "");
  // Opened from a bill reminder: show the bills.
  useEffect(() => { if (params.kind !== undefined) { setKind(params.kind); setPage(1); } }, [params.kind]);
  const [store, setStore] = useState("");
  const [page, setPage] = useState(1);
  const [opening, setOpening] = useState<string | null>(null);
  const q = useDocuments({ kind: kind || undefined, store_id: store || undefined, page, page_size: 30 });

  async function open(d: DocumentRow) {
    setOpening(d.id);
    try {
      await openRemoteFile(`/external/documents/${d.id}/file`, `${KIND_NAME[d.kind]}-${d.month.slice(0, 7)}`);
    } catch (e) {
      Alert.alert("Couldn't open the file", e instanceof Error ? e.message : "Please try again.");
    } finally {
      setOpening(null);
    }
  }

  return (
    <Screen onRefresh={() => q.refetch()} refreshing={q.isRefetching && !q.isLoading}>
      <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: 12, marginBottom: 14 }}>
        <Text style={[font.small, { flex: 1 }]}>Cards, bills and payment proofs.</Text>
        <Button title="Upload" onPress={() => router.push("/documents/upload")} icon={<Ionicons name="cloud-upload-outline" size={19} color="#fff" />} style={{ minHeight: 42, paddingHorizontal: 16 }} />
      </View>
      <View style={{ gap: 12 }}>
        <Chips options={KINDS} value={kind} onChange={(v) => { setKind(v); setPage(1); }} />
        <StorePicker value={store} allLabel="All my stores" label="Showing" onChange={(v) => { setStore(v); setPage(1); }} />
      </View>

      <View style={{ marginTop: 16 }}>
        {q.isLoading ? <ListSkeleton /> : q.isError ? <ErrorNote message={q.error.message} onRetry={() => q.refetch()} /> : q.data!.items.length === 0 ? (
          <Empty title="No documents" text="Upload a compliance card or payment proof to see it here." />
        ) : (
          <View style={{ gap: 10 }}>
            {q.data!.items.map((d) => (
              <Card key={d.id}>
                <View style={{ flexDirection: "row", alignItems: "flex-start", gap: 12 }}>
                  <IconTile icon={KIND_ICON[d.kind]} bg={d.kind === "bill" ? colors.warningSoft : d.kind === "payment" ? colors.successSoft : colors.brand50} fg={d.kind === "bill" ? colors.warning : d.kind === "payment" ? colors.success : colors.brand600} />
                  <View style={{ flex: 1 }}>
                    <View style={{ flexDirection: "row", alignItems: "flex-start", justifyContent: "space-between", gap: 10 }}>
                      <Text style={{ flex: 1, fontSize: 15, fontWeight: "700", color: colors.text }}>{KIND_NAME[d.kind]} · {fmtMonth(d.month)}</Text>
                      <BillState d={d} />
                    </View>
                    <Text numberOfLines={1} style={[font.small, { marginTop: 4 }]}>{d.store_name} · {fmtSize(d.size_bytes)}</Text>
                  </View>
                </View>
                <Pressable
                  onPress={() => open(d)}
                  disabled={opening === d.id}
                  accessibilityRole="button"
                  accessibilityLabel={`Open ${KIND_NAME[d.kind]}`}
                  hitSlop={8}
                  style={({ pressed }) => ({ marginTop: 12, minHeight: 44, borderRadius: radius.md, backgroundColor: pressed ? colors.brand100 : colors.brand50, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 8 })}
                >
                  <Ionicons name="open-outline" size={18} color={colors.brand600} />
                  <Text style={{ color: colors.brand700, fontWeight: "700", fontSize: 15 }}>{opening === d.id ? "Opening…" : "Open file"}</Text>
                </Pressable>
              </Card>
            ))}
          </View>
        )}
        {q.data && <Pager page={page} pageSize={q.data.page_size} total={q.data.total} onPage={setPage} />}
      </View>
    </Screen>
  );
}
