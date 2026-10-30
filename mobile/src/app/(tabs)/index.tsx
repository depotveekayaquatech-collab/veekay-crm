import { Pressable, Text, View } from "react-native";
import { Link, useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useAuth } from "@/auth/AuthProvider";
import { useBottles, useDailyOrders, useDocuments, useStores, useTickets } from "@/api/hooks";
import { Button, Card, ErrorNote, ListSkeleton, Screen, SectionTitle } from "@/components/ui";
import { daysAgo, fmtDate, fmtNumber, niceName } from "@/lib/format";
import { colors, font, radius } from "@/theme";

type IconName = React.ComponentProps<typeof Ionicons>["name"];
type Tone = "brand" | "ok" | "warn" | "bad";
const tones = (): Record<Tone, [string, string]> => ({
  brand: [colors.brand50, colors.brand600], ok: [colors.successSoft, colors.success], warn: [colors.warningSoft, colors.warning], bad: [colors.dangerSoft, colors.danger],
});

function Tile({ href, label, value, icon, tone }: { href: string; label: string; value: number | undefined; icon: IconName; tone: Tone }) {
  const router = useRouter();
  const [bg, fg] = tones()[tone];
  return (
    <Card onPress={() => router.push(href as never)} label={`${label}: ${value ?? "loading"}`} style={{ flex: 1, gap: 14 }}>
      <View style={{ width: 38, height: 38, borderRadius: radius.md, backgroundColor: bg, alignItems: "center", justifyContent: "center" }}>
        <Ionicons name={icon} size={20} color={fg} />
      </View>
      <View>
        <Text style={{ fontSize: 26, fontWeight: "800", color: colors.text }}>{value === undefined ? "–" : fmtNumber(value)}</Text>
        <Text style={font.small}>{label}</Text>
      </View>
    </Card>
  );
}

export default function Home() {
  const { account } = useAuth();
  const router = useRouter();
  const qc = useQueryClient();
  const [refreshing, setRefreshing] = useState(false);
  const isPoc = account?.kind === "poc";

  const stores = useStores();
  const week = useDailyOrders({ date_from: daysAgo(6), date_to: daysAgo(0) });
  const bottles = useBottles({ page_size: 1 });
  const open = useTickets({ status: "OPEN", page_size: 1 });
  const progress = useTickets({ status: "IN_PROGRESS", page_size: 1 });
  const bills = useDocuments({ kind: "bill", page_size: 100 });

  const today = daysAgo(0);
  const pending = (bills.data?.items ?? []).filter((d) => d.status === "PENDING");
  const overdue = pending.filter((d) => d.due_date && d.due_date <= today);
  const active = open.data && progress.data ? open.data.total + progress.data.total : undefined;
  const weekTotal = week.data?.reduce((n, d) => n + d.bottles, 0);
  const latest = week.data?.[0];

  async function refresh() {
    setRefreshing(true);
    await qc.invalidateQueries();
    setRefreshing(false);
  }

  return (
    <Screen onRefresh={refresh} refreshing={refreshing}>
      <View style={{ backgroundColor: colors.ink950, borderRadius: 22, padding: 20, overflow: "hidden" }}>
        <View style={{ position: "absolute", top: -70, left: -50, width: 200, height: 200, borderRadius: 100, backgroundColor: colors.brand500, opacity: 0.4 }} />
        <View style={{ position: "absolute", bottom: -80, right: -40, width: 190, height: 190, borderRadius: 95, backgroundColor: colors.aqua500, opacity: 0.35 }} />
        <View style={{ alignSelf: "flex-start", backgroundColor: "rgba(255,255,255,0.12)", borderRadius: 999, paddingHorizontal: 10, paddingVertical: 4 }}>
          <Text style={{ color: colors.aqua200, fontSize: 12, fontWeight: "700" }}>{isPoc ? "Store POC" : "Vendor"}</Text>
        </View>
        <Text style={{ color: colors.white, fontSize: 22, fontWeight: "800", marginTop: 12 }}>Hello, {niceName(account?.full_name ?? "").split(" ")[0]}</Text>
        <Text style={{ color: "rgba(255,255,255,0.7)", marginTop: 2 }}>{account?.store_count} store{account?.store_count === 1 ? "" : "s"} on your login</Text>
        <View style={{ flexDirection: "row", alignItems: "flex-end", justifyContent: "space-between", marginTop: 20, gap: 12 }}>
          <View>
            <Text style={{ color: "rgba(255,255,255,0.6)", fontSize: 12 }}>Bottles delivered, last 7 days</Text>
            <Text style={{ color: colors.white, fontSize: 38, fontWeight: "800", letterSpacing: -1 }}>{weekTotal === undefined ? "–" : fmtNumber(weekTotal)}</Text>
          </View>
          {latest ? (
            <View style={{ backgroundColor: "rgba(255,255,255,0.12)", borderRadius: radius.md, paddingHorizontal: 12, paddingVertical: 8, alignItems: "flex-end" }}>
              <Text style={{ color: "rgba(255,255,255,0.6)", fontSize: 11 }}>{fmtDate(latest.order_date)}</Text>
              <Text style={{ color: colors.white, fontSize: 16, fontWeight: "700" }}>{fmtNumber(latest.bottles)}</Text>
            </View>
          ) : null}
        </View>
      </View>

      {isPoc ? (
        <View style={{ flexDirection: "row", gap: 12, marginTop: 16 }}>
          <Button title="Confirm delivery" onPress={() => router.push("/deliveries/new")} icon={<Ionicons name="checkmark-circle-outline" size={20} color="#fff" />} style={{ flex: 1 }} />
          <Button title="Raise ticket" variant="secondary" onPress={() => router.push("/tickets/new")} icon={<Ionicons name="ticket-outline" size={20} color={colors.brand700} />} style={{ flex: 1 }} />
        </View>
      ) : (
        <View style={{ marginTop: 16, padding: 14, borderRadius: radius.md, backgroundColor: colors.brand50 }}>
          <Text style={{ color: colors.brand800, lineHeight: 20 }}>Your store POCs confirm deliveries and raise tickets. You can follow all of it here.</Text>
        </View>
      )}

      <View style={{ flexDirection: "row", gap: 12, marginTop: 16 }}>
        <Tile href="/bottles" label="Bottles at your stores" value={bottles.data?.total} icon="cube-outline" tone="brand" />
        <Tile href="/tickets" label="Active tickets" value={active} icon="ticket-outline" tone={active ? "warn" : "ok"} />
      </View>
      <View style={{ flexDirection: "row", gap: 12, marginTop: 12 }}>
        <Tile href="/documents" label="Bills to clear" value={bills.data ? pending.length : undefined} icon="receipt-outline" tone={overdue.length ? "bad" : pending.length ? "warn" : "ok"} />
        <Tile href="/stores" label="Your stores" value={account?.store_count} icon="storefront-outline" tone="brand" />
      </View>

      {overdue.length > 0 && (
        <View style={{ marginTop: 12, padding: 14, borderRadius: radius.md, backgroundColor: colors.dangerSoft }}>
          <Text style={{ color: colors.danger, fontWeight: "600", lineHeight: 20 }}>
            {overdue.length} bill{overdue.length === 1 ? " is" : "s are"} past the due date. The oldest was due {fmtDate(overdue.map((d) => d.due_date!).sort()[0])}.
          </Text>
        </View>
      )}

      <SectionTitle action={<Link href="/stores" style={{ color: colors.brand600, fontWeight: "700" }}>See all</Link>}>Your stores</SectionTitle>
      {stores.isLoading ? <ListSkeleton rows={3} /> : stores.isError ? <ErrorNote message={stores.error.message} onRetry={() => stores.refetch()} /> : (
        <Card style={{ padding: 0, overflow: "hidden" }}>
          {stores.data?.slice(0, 5).map((s, i) => (
            <Pressable
              key={s.id}
              onPress={() => router.push({ pathname: "/orders", params: { store: s.id } })}
              accessibilityRole="button"
              android_ripple={{ color: colors.brand100 }}
              style={{ minHeight: 60, paddingHorizontal: 16, paddingVertical: 12, borderTopWidth: i ? 1 : 0, borderTopColor: colors.border, flexDirection: "row", alignItems: "center", gap: 12 }}
            >
              <View style={{ flex: 1 }}>
                <Text numberOfLines={1} style={{ fontSize: 15, fontWeight: "600", color: colors.text }}>{s.name}</Text>
                <Text numberOfLines={1} style={font.small}>{s.code}{s.city ? ` · ${s.city}` : ""}</Text>
              </View>
              <Text style={{ fontSize: 12, fontWeight: "600", color: colors.textMuted }}>{bottles.data?.per_store[s.id] ?? 0} bottles</Text>
            </Pressable>
          ))}
          {(stores.data?.length ?? 0) > 5 && (
            <Link href="/stores" style={{ padding: 14, textAlign: "center", color: colors.brand600, fontWeight: "700", borderTopWidth: 1, borderTopColor: colors.border }}>
              View all {stores.data!.length} stores
            </Link>
          )}
        </Card>
      )}
    </Screen>
  );
}
