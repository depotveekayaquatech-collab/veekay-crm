import { useMemo, useState } from "react";
import { Alert, Text, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import { useCashList } from "@/api/staffHooks";
import { staffApi, type CashFilter, type CashPurchase } from "@/api/staff";
import { useAuth } from "@/auth/AuthProvider";
import { Badge, Button, Card, Chips, Empty, ErrorNote, ListSkeleton, Pager, Screen } from "@/components/ui";
import { openRemoteFile } from "@/lib/files";
import { fmtDate } from "@/lib/format";
import { colors, font, radius } from "@/theme";

const money = (v: string | number) => `₹${Number(v).toLocaleString("en-IN", { maximumFractionDigits: 2 })}`;

type Period = "month" | "today" | "30d" | "all";
type Kind = "all" | "OFFICE" | "STORE";

const ymd = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;

/** The date range for a period chip, in the phone's local calendar (the same days the purchases were entered on). */
function rangeOf(period: Period): Pick<CashFilter, "start" | "end"> {
  const now = new Date();
  if (period === "today") return { start: ymd(now), end: ymd(now) };
  if (period === "month") return { start: ymd(new Date(now.getFullYear(), now.getMonth(), 1)), end: ymd(now) };
  if (period === "30d") return { start: ymd(new Date(now.getFullYear(), now.getMonth(), now.getDate() - 29)), end: ymd(now) };
  return {};
}

const PERIOD_LABEL: Record<Period, string> = { month: "This month", today: "Today", "30d": "Last 30 days", all: "All time" };

export default function Cash() {
  const { hasPermission } = useAuth();
  const router = useRouter();
  const [page, setPage] = useState(1);
  const [period, setPeriod] = useState<Period>("month");
  const [kind, setKind] = useState<Kind>("all");
  const [downloading, setDownloading] = useState(false);
  const canSheet = hasPermission("cash.view");   // the server enforces this too
  const filter = useMemo<CashFilter>(() => ({ ...rangeOf(period), ...(kind === "all" ? {} : { kind }) }), [period, kind]);
  const q = useCashList(page, filter);

  async function downloadSheet() {
    if (downloading) return;
    setDownloading(true);
    try {
      await openRemoteFile(staffApi.cashSheetPath(filter), `expenses-${PERIOD_LABEL[period].toLowerCase().replace(/\s+/g, "-")}`);
    } catch (e) {
      Alert.alert("Couldn't get the sheet", e instanceof Error ? e.message : "Please try again.");
    } finally {
      setDownloading(false);
    }
  }

  // Group by date, newest first (like an expense app's feed).
  const groups = new Map<string, CashPurchase[]>();
  for (const p of q.data?.items ?? []) groups.set(p.purchase_date, [...(groups.get(p.purchase_date) ?? []), p]);

  return (
    <Screen onRefresh={() => q.refetch()} refreshing={q.isRefetching && !q.isLoading} padBottom={110}>
      <Chips<Period>
        value={period}
        onChange={(v) => { setPeriod(v); setPage(1); }}
        options={(Object.keys(PERIOD_LABEL) as Period[]).map((v) => ({ label: PERIOD_LABEL[v], value: v }))}
      />
      <View style={{ marginTop: 8 }}>
        <Chips<Kind>
          value={kind}
          onChange={(v) => { setKind(v); setPage(1); }}
          options={[{ label: "All", value: "all" }, { label: "Office", value: "OFFICE" }, { label: "Stores", value: "STORE" }]}
        />
      </View>

      <Card style={{ backgroundColor: colors.ink950, borderColor: colors.ink950, marginTop: 14 }}>
        <Text style={{ color: "rgba(255,255,255,0.65)", fontSize: 12 }}>{canSheet ? "Total expenses" : "Total of your purchases"} · {PERIOD_LABEL[period]}</Text>
        <Text style={{ color: colors.white, fontSize: 32, fontWeight: "800", marginTop: 2 }}>{q.data ? money(q.data.amount_total) : "–"}</Text>
        <Text style={{ color: "rgba(255,255,255,0.55)", fontSize: 12, marginTop: 2 }}>{q.data ? `${q.data.total} purchase${q.data.total === 1 ? "" : "s"}` : ""}</Text>
        {q.data ? (
          <View style={{ flexDirection: "row", gap: 12, marginTop: 12 }}>
            <View style={{ flex: 1, backgroundColor: "rgba(255,255,255,0.1)", borderRadius: radius.md, padding: 10 }}>
              <Text style={{ color: "rgba(255,255,255,0.6)", fontSize: 11 }}>Office</Text>
              <Text style={{ color: colors.white, fontSize: 16, fontWeight: "800" }}>{money(q.data.office_total)}</Text>
            </View>
            <View style={{ flex: 1, backgroundColor: "rgba(255,255,255,0.1)", borderRadius: radius.md, padding: 10 }}>
              <Text style={{ color: "rgba(255,255,255,0.6)", fontSize: 11 }}>Stores</Text>
              <Text style={{ color: colors.white, fontSize: 16, fontWeight: "800" }}>{money(q.data.store_total)}</Text>
            </View>
          </View>
        ) : null}
      </Card>

      {canSheet && (
        <Button title="Download expense sheet (Excel)" variant="secondary" onPress={() => void downloadSheet()} loading={downloading} disabled={!q.data || q.data.total === 0}
          icon={<Ionicons name="download-outline" size={20} color={colors.brand600} />} style={{ marginTop: 14 }} />
      )}

      {hasPermission("cash.add") && (
        <Button title="Add a purchase" onPress={() => router.push("/staff/expense/new")} icon={<Ionicons name="add-circle-outline" size={22} color="#fff" />} style={{ marginTop: 14 }} />
      )}

      <View style={{ marginTop: 18 }}>
        {q.isLoading ? <ListSkeleton /> : q.isError ? <ErrorNote message={q.error.message} onRetry={() => q.refetch()} /> : q.data!.items.length === 0 ? (
          <Empty title="No purchases here" text={period === "all" && kind === "all" ? "Cash you spend for the office or a store goes here, with a photo of the bill." : "Nothing matches these filters. Try a longer period."} />
        ) : (
          [...groups.entries()].map(([date, rows]) => (
            <View key={date} style={{ marginBottom: 14 }}>
              <Text style={[font.small, { fontWeight: "700", marginBottom: 6 }]}>{fmtDate(date)}</Text>
              <Card style={{ padding: 0, overflow: "hidden" }}>
                {rows.map((p, i) => (
                  <View key={p.id} style={{ flexDirection: "row", alignItems: "center", gap: 12, padding: 14, borderTopWidth: i ? 1 : 0, borderTopColor: colors.border }}>
                    <View style={{ width: 40, height: 40, borderRadius: radius.md, backgroundColor: p.kind === "STORE" ? colors.brand50 : colors.warningSoft, alignItems: "center", justifyContent: "center" }}>
                      <Ionicons name={p.kind === "STORE" ? "storefront-outline" : "business-outline"} size={20} color={p.kind === "STORE" ? colors.brand600 : colors.warning} />
                    </View>
                    <View style={{ flex: 1 }}>
                      <Text numberOfLines={1} style={{ fontSize: 15, fontWeight: "700", color: colors.text }}>{p.category_label}{p.other_reason ? ` · ${p.other_reason}` : ""}</Text>
                      <Text numberOfLines={1} style={font.small}>{p.store_name ?? "Office"}{canSheet && p.added_by ? ` · ${p.added_by}` : ""}</Text>
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
