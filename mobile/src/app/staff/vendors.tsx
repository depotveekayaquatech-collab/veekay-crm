import { useMemo, useState } from "react";
import { FlatList, Pressable, Share, Text, TextInput, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useAuth } from "@/auth/AuthProvider";
import { useInsights, useVendorPerformance } from "@/api/adminHooks";
import type { VendorPerformance, VendorRow } from "@/api/admin";
import { Chips, Empty, ErrorNote, ListSkeleton } from "@/components/ui";
import { fmtMonth, isoDate } from "@/lib/format";
import { formatVendor, formatVendorReport } from "@/lib/vendorReport";
import { formatLimitReport, formatLimitVendor } from "@/lib/zeptoLimitReport";
import { colors, font, radius } from "@/theme";

const short = (iso: string) => new Date(`${iso}T00:00:00`).toLocaleDateString("en-IN", { day: "numeric", month: "short" });
const name = (v: VendorRow) => v.vendor_name ?? "(No vendor name)";

function shiftMonth(month: string, by: number): string {
  const [y, m] = month.split("-").map(Number);
  const d = new Date(y, m - 1 + by, 1);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

const isZepto = (d: VendorPerformance) => d.partner_slug === "zepto";
const to = (d: VendorPerformance) => (d.to ? ` (as on ${short(d.to)})` : "");
/** The message for these vendors: Zepto gets its monthly limit / supplied / pending-limit format, every other platform the bottle count. */
const report = (d: VendorPerformance, rows: VendorRow[]) =>
  isZepto(d) ? formatLimitReport(`${d.partner_label} - Vendor limit, ${d.month_label}${to(d)}`, rows) : formatVendorReport(`${d.partner_label} - Vendor bottle count, ${d.month_label}`, rows);

/** Opens the phone's share sheet with the text: WhatsApp is listed there, and so is "Copy". */
async function send(text: string) {
  try { await Share.share({ message: text }); } catch { /* the person closed the sheet, or the phone has no app to share with */ }
}

function ShareButton({ label, onPress, solid }: { label: string; onPress: () => void; solid?: boolean }) {
  return (
    <Pressable onPress={onPress} accessibilityRole="button" accessibilityLabel={label} hitSlop={6} android_ripple={{ color: colors.brand100 }}
      style={{ minHeight: 40, paddingHorizontal: 14, borderRadius: radius.md, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 6, backgroundColor: solid ? colors.brand600 : colors.brand50 }}>
      <Ionicons name="logo-whatsapp" size={17} color={solid ? colors.white : colors.brand600} />
      <Text style={{ fontWeight: "800", color: solid ? colors.white : colors.brand600 }}>{label}</Text>
    </Pressable>
  );
}

function VendorCard({ v, d }: { v: VendorRow; d: VendorPerformance }) {
  const [open, setOpen] = useState(false);
  const text = useMemo(() => report(d, [v]), [v, d]);
  return (
    <View style={{ backgroundColor: colors.surface, borderRadius: radius.lg, borderWidth: 1, borderColor: colors.border, padding: 14, gap: 10 }}>
      <Pressable onPress={() => setOpen((o) => !o)} accessibilityRole="button" accessibilityState={{ expanded: open }} accessibilityLabel={`${name(v)}, ${v.bottles} bottles`}
        style={{ flexDirection: "row", alignItems: "center", gap: 10 }}>
        <View style={{ flex: 1 }}>
          <Text style={{ fontSize: 15, fontWeight: "700", color: colors.text }}>{name(v)}</Text>
          <Text style={font.small}>{v.store_count} store{v.store_count === 1 ? "" : "s"}{v.vendor_number ? ` · ${v.vendor_number}` : ""}</Text>
        </View>
        <Text style={{ fontSize: 20, fontWeight: "800", color: colors.text }}>{v.bottles.toLocaleString("en-IN")}</Text>
        <Ionicons name={open ? "chevron-up" : "chevron-down"} size={16} color={colors.textFaint} />
      </Pressable>
      {open && (
        <View style={{ gap: 6 }}>
          {v.stores.map((s) => (
            <View key={s.store_id} style={{ flexDirection: "row", alignItems: "center", gap: 10 }}>
              <View style={{ flex: 1 }}>
                <Text numberOfLines={2} style={{ fontSize: 14, color: colors.text }}>{s.store_name}</Text>
                <Text style={font.tiny}>{s.external_code}{s.live ? "" : " · not live"} · {s.days_marked} day{s.days_marked === 1 ? "" : "s"} marked</Text>
              </View>
              <Text style={{ fontSize: 15, fontWeight: "800", color: colors.text }}>{s.bottles.toLocaleString("en-IN")}</Text>
            </View>
          ))}
          <Text selectable style={[font.small, { marginTop: 4, padding: 10, borderRadius: radius.md, backgroundColor: colors.surfaceSubtle, color: colors.text }]}>{isZepto(d) ? formatLimitVendor(v) : formatVendor(v)}</Text>
        </View>
      )}
      <ShareButton label="Send to vendor" onPress={() => void send(text)} />
    </View>
  );
}

/**
 * Bottles marked at each vendor's stores this month (1st to today). An employee sees the vendors of their own stores; someone with the daily
 * overview sees the whole platform. "Send" opens the phone's share sheet, so the text can go to the vendor's WhatsApp chat or be copied.
 */
export default function Vendors() {
  const { staff, hasPermission } = useAuth();
  const overview = hasPermission("orders.overview");
  const ins = useInsights(overview);                           // only people with the daily overview may list the platforms
  const platforms = overview ? (ins.data?.platforms ?? []).map((p) => ({ slug: p.slug, label: p.label })) : staff?.platform_slug ? [{ slug: staff.platform_slug, label: staff.platform_label ?? staff.platform_slug }] : [];
  const [picked, setPicked] = useState("");
  const partner = platforms.some((p) => p.slug === picked) ? picked : (platforms[0]?.slug ?? "");
  const [month, setMonth] = useState("");                       // "" = the server's default: this month
  const [needle, setNeedle] = useState("");
  const q = useVendorPerformance(partner, month);
  const d = q.data;
  const thisMonth = isoDate(new Date()).slice(0, 7);
  const shown = d?.month ?? month;

  const rows = useMemo(() => {
    const n = needle.trim().toLowerCase();
    return (d?.vendors ?? []).filter((v) => !n || name(v).toLowerCase().includes(n) || (v.vendor_number ?? "").includes(n) || v.stores.some((s) => s.store_name.toLowerCase().includes(n)));
  }, [d, needle]);

  const header = (
    <View style={{ gap: 12, marginBottom: 4 }}>
      {platforms.length > 1 && <Chips options={platforms.map((p) => ({ label: p.label, value: p.slug }))} value={partner} onChange={setPicked} />}
      <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between", backgroundColor: colors.surface, borderRadius: radius.lg, borderWidth: 1, borderColor: colors.border, paddingHorizontal: 8, height: 52 }}>
        <Pressable disabled={!shown} onPress={() => setMonth(shiftMonth(shown, -1))} accessibilityRole="button" accessibilityLabel="Previous month" hitSlop={10} style={{ padding: 8 }}><Ionicons name="chevron-back" size={20} color={colors.text} /></Pressable>
        <Text style={{ fontSize: 16, fontWeight: "800", color: colors.text }}>{shown ? fmtMonth(`${shown}-01`) : "…"}</Text>
        <Pressable disabled={!shown || shown >= thisMonth} onPress={() => setMonth(shiftMonth(shown, 1))} accessibilityRole="button" accessibilityLabel="Next month" hitSlop={10} style={{ padding: 8, opacity: !shown || shown >= thisMonth ? 0.3 : 1 }}><Ionicons name="chevron-forward" size={20} color={colors.text} /></Pressable>
      </View>
      {d && (
        <View style={{ backgroundColor: colors.ink950, borderRadius: radius.xl, padding: 16 }}>
          <Text style={{ color: "rgba(255,255,255,0.65)", fontSize: 12 }}>{d.partner_label} · bottles marked{d.from && d.to ? ` · ${short(d.from)} to ${short(d.to)}` : ""}</Text>
          <Text style={{ color: colors.white, fontSize: 32, fontWeight: "800" }}>{d.summary.bottles.toLocaleString("en-IN")}</Text>
          <Text style={{ color: "rgba(255,255,255,0.7)", fontSize: 13, marginTop: 2 }}>{d.summary.vendors} vendor{d.summary.vendors === 1 ? "" : "s"} · {d.summary.stores.toLocaleString("en-IN")} stores</Text>
        </View>
      )}
      {d && rows.length > 0 && <ShareButton solid label={rows.length === d.vendors.length ? "Send all vendors" : `Send these ${rows.length} vendors`} onPress={() => void send(report(d, rows))} />}
      <View style={{ flexDirection: "row", alignItems: "center", gap: 8, height: 48, borderRadius: radius.md, backgroundColor: colors.surface, borderWidth: 1.5, borderColor: colors.border, paddingHorizontal: 12 }}>
        <Ionicons name="search" size={18} color={colors.textFaint} />
        <TextInput value={needle} onChangeText={setNeedle} placeholder="Search vendor, number or store" placeholderTextColor={colors.textFaint} accessibilityLabel="Search" style={{ flex: 1, fontSize: 16, color: colors.text }} />
      </View>
    </View>
  );

  return (
    <View style={{ flex: 1, backgroundColor: colors.surfaceSubtle }}>
      <FlatList
        data={rows}
        keyExtractor={(v) => name(v)}
        keyboardShouldPersistTaps="handled"
        onRefresh={() => q.refetch()}
        refreshing={q.isRefetching && !q.isLoading}
        contentContainerStyle={{ padding: 16, paddingBottom: 40, gap: 10 }}
        ListHeaderComponent={header}
        ListEmptyComponent={
          !partner && !ins.isLoading ? <Empty title="No platform" text="Your profile has no platform yet, so there are no vendors to show." />
          : q.isLoading || ins.isLoading ? <ListSkeleton />
          : q.isError ? <ErrorNote message={q.error.message} onRetry={() => q.refetch()} />
          : <Empty title="No vendors" text={needle ? "Try another name." : "None of your stores has a vendor with bottles yet."} />
        }
        renderItem={({ item }) => <VendorCard v={item} d={d!} />}
      />
    </View>
  );
}
