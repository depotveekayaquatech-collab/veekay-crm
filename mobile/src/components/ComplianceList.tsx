import { useEffect, useState } from "react";
import { FlatList, Pressable, Text, TextInput, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import type { ComplianceRow } from "@/api/complianceApi";
import { useComplianceList } from "@/api/complianceHooks";
import { DocUploadSheet } from "@/components/DocUploadSheet";
import { Badge, Button, Chips, Empty, ErrorNote, ListSkeleton, Pager } from "@/components/ui";
import { KIND_LABEL, KINDS, KIND_UPLOAD, monthLabel, STATUS_LABEL, STATUS_TONE, type ComplianceStatus, type DocKind } from "@/lib/compliance";
import { colors, font, radius, shadow } from "@/theme";

type Filter = "all" | ComplianceStatus | "missing";

function useDebounced<T>(value: T, ms: number): T {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return v;
}

/**
 * The existing monthly compliance list, on a phone. `focus="card"` is the Cards view: the same stores, the same records, showing
 * only the card and offering "Upload card photo" on each row. The server decides which stores a person may see.
 */
export function ComplianceList({ focus }: { focus?: DocKind }) {
  const router = useRouter();
  const [month, setMonth] = useState("");
  const [needle, setNeedle] = useState("");
  const [filter, setFilter] = useState<Filter>("all");
  const [page, setPage] = useState(1);
  const [sheet, setSheet] = useState<{ row: ComplianceRow; kind: DocKind; replacing: boolean } | null>(null);
  const q = useDebounced(needle.trim(), 350);

  const query = useComplianceList({
    month: month || undefined,
    q: q || undefined,
    page,
    page_size: 20,
    status: filter === "PENDING" || filter === "PARTIAL" || filter === "COMPLETE" ? filter : undefined,
    missing: filter === "missing" ? focus ?? "any" : undefined,
  });
  const data = query.data;
  const k = data?.kpis;
  const shownKinds = focus ? [focus] : KINDS;
  const logged = focus === "card" ? k?.card_logged : focus === "bill" ? k?.invoice_logged : focus === "payment" ? k?.payment_logged : undefined;
  const percent = focus ? (k && k.total ? Math.round(((logged ?? 0) / k.total) * 100) : 0) : Math.round(k?.compliance_percent ?? 0);
  const monthNow = data?.month ?? month;

  const open = (r: ComplianceRow) =>
    router.push({ pathname: "/staff/store-docs/[storeId]", params: { storeId: r.store_id, code: r.external_code, name: r.name, month: monthNow, ...(focus ? { focus } : {}) } });

  const header = (
    <View style={{ gap: 14, marginBottom: 8 }}>
      {data && data.months.length > 1 ? (
        <Chips options={data.months.map((m) => ({ value: m, label: monthLabel(m, false) }))} value={monthNow} onChange={(m) => { setMonth(m); setPage(1); }} />
      ) : null}

      <View style={{ backgroundColor: colors.ink950, borderRadius: radius.xl, padding: 18, gap: 12 }}>
        <Text style={{ color: "rgba(255,255,255,0.65)", fontSize: 12 }}>
          {focus ? `${KIND_LABEL[focus]}s on file` : "Compliance"} · {monthNow ? monthLabel(monthNow) : "…"}
        </Text>
        <View style={{ flexDirection: "row", alignItems: "flex-end", justifyContent: "space-between" }}>
          <Text style={{ color: colors.white, fontSize: 30, fontWeight: "800" }}>
            {focus ? logged ?? 0 : `${percent}%`}
            <Text style={{ fontSize: 15, color: "rgba(255,255,255,0.6)", fontWeight: "600" }}>{focus ? ` of ${k?.total ?? 0} stores` : " complete"}</Text>
          </Text>
          {focus ? <Text style={{ color: colors.aqua200, fontSize: 18, fontWeight: "800" }}>{percent}%</Text> : null}
        </View>
        <View style={{ height: 8, borderRadius: 4, backgroundColor: "rgba(255,255,255,0.15)", overflow: "hidden" }}>
          <View style={{ height: 8, borderRadius: 4, backgroundColor: colors.brand500, width: `${percent}%` }} />
        </View>
        {!focus && k ? (
          <View style={{ flexDirection: "row", gap: 8 }}>
            {([["Cards", k.card_logged], ["Invoices", k.invoice_logged], ["Payments", k.payment_logged]] as const).map(([label, n]) => (
              <View key={label} style={{ flex: 1, backgroundColor: "rgba(255,255,255,0.08)", borderRadius: radius.md, paddingVertical: 8, alignItems: "center" }}>
                <Text style={{ color: colors.white, fontWeight: "800", fontSize: 16 }}>{n}<Text style={{ color: "rgba(255,255,255,0.55)", fontSize: 12 }}>/{k.total}</Text></Text>
                <Text style={{ color: "rgba(255,255,255,0.65)", fontSize: 11 }}>{label}</Text>
              </View>
            ))}
          </View>
        ) : null}
      </View>

      <View style={{ flexDirection: "row", alignItems: "center", gap: 8, height: 50, borderRadius: radius.md, backgroundColor: colors.surface, borderWidth: 1.5, borderColor: colors.border, paddingHorizontal: 12 }}>
        <Ionicons name="search" size={18} color={colors.textFaint} />
        <TextInput
          value={needle}
          onChangeText={(t) => { setNeedle(t); setPage(1); }}
          placeholder="Search store name or code"
          placeholderTextColor={colors.textFaint}
          accessibilityLabel="Search stores"
          returnKeyType="search"
          autoCorrect={false}
          style={{ flex: 1, fontSize: 16, color: colors.text }}
        />
        {needle ? (
          <Pressable onPress={() => { setNeedle(""); setPage(1); }} accessibilityRole="button" accessibilityLabel="Clear search" hitSlop={10}>
            <Ionicons name="close-circle" size={20} color={colors.textFaint} />
          </Pressable>
        ) : null}
      </View>

      <Chips<Filter>
        options={focus
          ? [{ label: "All stores", value: "all" }, { label: `Missing ${KIND_LABEL[focus].toLowerCase()}`, value: "missing" }]
          : [{ label: "All", value: "all" }, { label: "Nothing logged", value: "PENDING" }, { label: "Partly done", value: "PARTIAL" }, { label: "Complete", value: "COMPLETE" }]}
        value={filter}
        onChange={(v) => { setFilter(v); setPage(1); }}
      />
      {data ? <Text style={font.small}>{data.total} store{data.total === 1 ? "" : "s"}{q ? ` matching “${q}”` : ""}</Text> : null}
    </View>
  );

  return (
    <View style={{ flex: 1, backgroundColor: colors.surfaceSubtle }}>
      <FlatList
        data={data?.items ?? []}
        keyExtractor={(r) => r.store_id}
        keyboardShouldPersistTaps="handled"
        onRefresh={() => void query.refetch()}
        refreshing={query.isRefetching && !query.isLoading}
        contentContainerStyle={{ padding: 16, paddingBottom: 40, gap: 10 }}
        ListHeaderComponent={header}
        ListEmptyComponent={
          query.isLoading ? <ListSkeleton /> : query.isError ? <ErrorNote message={query.error.message} onRetry={() => void query.refetch()} /> : (
            <Empty
              icon={q || filter !== "all" ? "search-outline" : "storefront-outline"}
              title={q || filter !== "all" ? "No store matches" : "No stores to show"}
              text={q || filter !== "all" ? "Try a different search or filter." : "Stores you look after will appear here once they are live."}
            />
          )
        }
        ListFooterComponent={data ? <Pager page={data.page} pageSize={data.page_size} total={data.total} onPage={setPage} /> : null}
        renderItem={({ item: r }) => (
          <Pressable
            onPress={() => open(r)}
            accessibilityRole="button"
            accessibilityLabel={`${r.name}, ${r.external_code}. ${STATUS_LABEL[r.status]}.`}
            android_ripple={{ color: colors.brand100 }}
            style={{ backgroundColor: colors.surface, borderRadius: radius.lg, borderWidth: 1, borderColor: colors.border, padding: 14, gap: 10, ...shadow.card }}
          >
            <View style={{ flexDirection: "row", alignItems: "center", gap: 10 }}>
              <View style={{ flex: 1 }}>
                <Text numberOfLines={1} style={{ fontSize: 15, fontWeight: "700", color: colors.text }}>{r.name}</Text>
                <Text numberOfLines={1} style={font.small}>{r.external_code}{r.city ? ` · ${r.city}` : ""}</Text>
              </View>
              {focus ? null : <Badge tone={STATUS_TONE[r.status]}>{r.percent}%</Badge>}
              <Ionicons name="chevron-forward" size={18} color={colors.textFaint} />
            </View>
            <View style={{ flexDirection: "row", gap: 8 }}>
              {shownKinds.map((kind) => {
                const on = !!r[kind];
                return (
                  <View key={kind} style={{ flexDirection: "row", alignItems: "center", gap: 4, paddingHorizontal: 10, minHeight: 28, borderRadius: radius.pill, backgroundColor: on ? colors.successSoft : colors.surfaceMuted }}>
                    <Ionicons name={on ? "checkmark-circle" : "ellipse-outline"} size={14} color={on ? colors.success : colors.textFaint} />
                    <Text style={{ fontSize: 12, fontWeight: "700", color: on ? colors.success : colors.textMuted }}>{KIND_LABEL[kind]}</Text>
                  </View>
                );
              })}
            </View>
            {focus ? (
              <Button
                title={r[focus] ? "Upload new photo" : KIND_UPLOAD[focus]}
                variant={r[focus] ? "secondary" : "primary"}
                icon={<Ionicons name="camera-outline" size={20} color={r[focus] ? colors.brand700 : colors.white} />}
                onPress={() => setSheet({ row: r, kind: focus, replacing: !!r[focus] })}
              />
            ) : null}
          </Pressable>
        )}
      />
      {sheet && monthNow ? (
        <DocUploadSheet
          store={{ id: sheet.row.store_id, name: sheet.row.name, code: sheet.row.external_code }}
          month={monthNow}
          kind={sheet.kind}
          replacing={sheet.replacing}
          onClose={() => setSheet(null)}
        />
      ) : null}
    </View>
  );
}

