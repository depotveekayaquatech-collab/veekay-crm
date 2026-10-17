import { useMemo, useState } from "react";
import { Alert, KeyboardAvoidingView, Platform, Pressable, ScrollView, Text, TextInput, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { Stack, useLocalSearchParams, useRouter } from "expo-router";
import * as Haptics from "expo-haptics";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useCalendar, useMarkMany } from "@/api/staffHooks";
import { Button, Card, ErrorNote, ListSkeleton } from "@/components/ui";
import { MonthGrid, type CellState } from "@/components/MonthGrid";
import { daysAgo } from "@/lib/format";
import { colors, font, radius } from "@/theme";

const MAX = 200;

const dayLabel = (iso: string) => new Date(`${iso}T00:00:00`).toLocaleDateString("en-IN", { weekday: "short", day: "numeric", month: "short" });
const valid = (v: string | undefined) => v !== undefined && /^\d{1,3}$/.test(v) && Number(v) <= MAX;

function Stepper({ value, onChange, error, label }: { value: string; onChange: (v: string) => void; error?: boolean; label: string }) {
  const n = /^\d+$/.test(value) ? Number(value) : null;
  const step = (d: number) => onChange(String(Math.min(MAX, Math.max(0, (n ?? 0) + d))));
  const btn = { width: 40, height: 40, borderRadius: radius.md, backgroundColor: colors.surfaceMuted, alignItems: "center" as const, justifyContent: "center" as const };
  return (
    <View style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
      <Pressable onPress={() => step(-1)} accessibilityRole="button" accessibilityLabel={`Less for ${label}`} style={btn} hitSlop={4}><Ionicons name="remove" size={20} color={colors.text} /></Pressable>
      <TextInput
        value={value}
        onChangeText={(t) => onChange(t.replace(/\D/g, "").slice(0, 3))}
        keyboardType="number-pad"
        placeholder="0"
        placeholderTextColor={colors.textFaint}
        accessibilityLabel={`Bottles for ${label}`}
        selectTextOnFocus
        style={{ width: 64, height: 44, textAlign: "center", fontSize: 18, fontWeight: "800", color: colors.text, borderRadius: radius.md, borderWidth: 1.5, borderColor: error ? colors.danger : colors.border, backgroundColor: colors.surface }}
      />
      <Pressable onPress={() => step(1)} accessibilityRole="button" accessibilityLabel={`More for ${label}`} style={btn} hitSlop={4}><Ionicons name="add" size={20} color={colors.text} /></Pressable>
    </View>
  );
}

export default function MarkMany() {
  const { storeId, day } = useLocalSearchParams<{ storeId: string; day?: string }>();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const cal = useCalendar(storeId);
  const mark = useMarkMany();
  const [picked, setPicked] = useState<string[] | null>(null);
  const [values, setValues] = useState<Record<string, string>>({});
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [same, setSame] = useState("");

  const byDate = useMemo(() => new Map((cal.data?.days ?? []).map((d) => [d.date, d])), [cal.data]);
  const open = useMemo(() => (cal.data?.days ?? []).filter((d) => !d.marked && !d.is_future).map((d) => d.date), [cal.data]);
  const today = cal.data?.days.find((d) => d.is_today)?.date;
  const yesterday = daysAgo(1);

  // Opened from the Orders list: the day that list was showing is already ticked, ready for its count.
  const initial = useMemo(() => {
    const d = day ? byDate.get(day) : undefined;
    return day && d && !d.marked && !d.is_future ? [day] : [];
  }, [day, byDate]);
  const selected = picked ?? initial;
  const setSelected = (next: string[] | ((s: string[]) => string[])) => setPicked((p) => (typeof next === "function" ? next(p ?? initial) : next));

  function toggle(iso: string) {
    Haptics.selectionAsync().catch(() => undefined);
    setErrors((e) => ({ ...e, [iso]: "" }));
    setSelected((s) => (s.includes(iso) ? s.filter((x) => x !== iso) : [...s, iso].sort()));
  }
  const add = (list: string[]) => setSelected((s) => [...new Set([...s, ...list])].sort());

  const allValid = selected.length > 0 && selected.every((d) => valid(values[d]));
  const total = selected.reduce((n, d) => n + (valid(values[d]) ? Number(values[d]) : 0), 0);

  function applySame() {
    if (!valid(same)) return;
    setValues((v) => ({ ...v, ...Object.fromEntries(selected.map((d) => [d, same])) }));
  }

  function submit() {
    Alert.alert(
      `Mark ${selected.length} date${selected.length === 1 ? "" : "s"}?`,
      `${total} bottles in total. You can't change a marked date yourself afterwards; an admin has to correct it.`,
      [
        { text: "Review", style: "cancel" },
        {
          text: "Mark orders",
          onPress: () =>
            mark.mutate(
              { store_id: storeId, entries: selected.map((d) => ({ order_date: d, bottle_count: Number(values[d]) })) },
              {
                onSuccess: (r) => {
                  const failed = r.results.filter((x) => !x.ok);
                  const done = new Set(r.results.filter((x) => x.ok).map((x) => x.order_date));
                  setSelected((s) => s.filter((d) => !done.has(d)));
                  setErrors(Object.fromEntries(failed.map((x) => [x.order_date, x.error ?? "Not saved"])));
                  if (failed.length === 0) {
                    Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success).catch(() => undefined);
                    Alert.alert("Marked", `${r.saved} date${r.saved === 1 ? "" : "s"} saved.`, [{ text: "Done", onPress: () => router.back() }]);
                  } else {
                    Haptics.notificationAsync(Haptics.NotificationFeedbackType.Warning).catch(() => undefined);
                    Alert.alert(`${r.saved} saved, ${failed.length} not saved`, "The dates that were not saved are still selected, with the reason shown.");
                  }
                },
                onError: (e) => Alert.alert("Couldn't mark orders", e.message),
              },
            ),
        },
      ],
    );
  }

  const state = (iso: string): CellState => {
    const d = byDate.get(iso);
    if (!d) return { disabled: true };
    return {
      disabled: d.marked || d.is_future,
      selected: selected.includes(iso),
      today: d.is_today,
      badge: d.marked ? d.count : null,
    };
  };

  return (
    <KeyboardAvoidingView style={{ flex: 1, backgroundColor: colors.surfaceSubtle }} behavior={Platform.OS === "ios" ? "padding" : undefined}>
      <Stack.Screen options={{ title: cal.data?.store_name ?? "Mark orders" }} />
      <ScrollView keyboardShouldPersistTaps="handled" contentContainerStyle={{ padding: 16, paddingBottom: 140 }}>
        {cal.isLoading ? <ListSkeleton rows={4} /> : cal.isError ? <ErrorNote message={cal.error.message} onRetry={() => cal.refetch()} /> : (
          <>
            <Text style={font.small}>{cal.data!.store_code} · {cal.data!.month_label}</Text>
            <Text style={[font.small, { marginTop: 2 }]}>Tap the dates to mark. Green numbers are already marked.</Text>

            <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 8, marginTop: 14 }}>
              {today && !byDate.get(today)?.marked ? <Shortcut label="Today" onPress={() => add([today])} /> : null}
              {byDate.get(yesterday) && !byDate.get(yesterday)!.marked ? <Shortcut label="Yesterday" onPress={() => add([yesterday])} /> : null}
              {open.length > 1 ? <Shortcut label={`All ${open.length} unmarked days`} onPress={() => add(open)} /> : null}
              {selected.length > 0 ? <Shortcut label="Clear" tone="plain" onPress={() => setSelected([])} /> : null}
            </View>

            <Card style={{ marginTop: 14, padding: 8 }}>
              <MonthGrid year={cal.data!.year} month={cal.data!.month} state={state} onPress={toggle} />
            </Card>

            {open.length === 0 ? (
              <View style={{ marginTop: 16, padding: 14, borderRadius: radius.md, backgroundColor: colors.successSoft }}>
                <Text style={{ color: colors.success, fontWeight: "700" }}>Every date up to today is marked for this store.</Text>
              </View>
            ) : null}

            {selected.length > 0 && (
              <>
                <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginTop: 22, marginBottom: 10 }}>
                  <Text style={font.h2}>Bottles per date</Text>
                  <Text style={font.small}>{selected.length} selected</Text>
                </View>

                <Card style={{ flexDirection: "row", alignItems: "center", gap: 10, padding: 12, backgroundColor: colors.brand50, borderColor: colors.brand100 }}>
                  <Text style={{ flex: 1, fontSize: 13, fontWeight: "600", color: colors.brand800 }}>Same count for all</Text>
                  <TextInput
                    value={same}
                    onChangeText={(t) => setSame(t.replace(/\D/g, "").slice(0, 3))}
                    keyboardType="number-pad"
                    placeholder="e.g. 20"
                    placeholderTextColor={colors.textFaint}
                    accessibilityLabel="Same count for all selected dates"
                    style={{ width: 80, height: 42, textAlign: "center", fontSize: 16, fontWeight: "700", color: colors.text, borderRadius: radius.md, borderWidth: 1.5, borderColor: colors.brand200, backgroundColor: colors.surface }}
                  />
                  <Button title="Fill" onPress={applySame} disabled={!valid(same)} style={{ minHeight: 42, paddingHorizontal: 18 }} />
                </Card>

                <View style={{ gap: 8, marginTop: 10 }}>
                  {selected.map((iso) => (
                    <Card key={iso} style={{ padding: 12, borderColor: errors[iso] ? colors.danger : colors.border }}>
                      <View style={{ flexDirection: "row", alignItems: "center", gap: 10 }}>
                        <View style={{ flex: 1 }}>
                          <Text style={{ fontSize: 15, fontWeight: "700", color: colors.text }}>{dayLabel(iso)}{iso === today ? "  · Today" : ""}</Text>
                        </View>
                        <Stepper value={values[iso] ?? ""} onChange={(v) => { setValues((s) => ({ ...s, [iso]: v })); setErrors((e) => ({ ...e, [iso]: "" })); }} error={!!errors[iso] || (values[iso] !== undefined && values[iso] !== "" && !valid(values[iso]))} label={dayLabel(iso)} />
                        <Pressable onPress={() => toggle(iso)} accessibilityRole="button" accessibilityLabel={`Remove ${dayLabel(iso)}`} hitSlop={8}>
                          <Ionicons name="close-circle" size={22} color={colors.textFaint} />
                        </Pressable>
                      </View>
                      {errors[iso] ? <Text style={{ color: colors.danger, fontSize: 13, marginTop: 8 }}>{errors[iso]}</Text> : null}
                    </Card>
                  ))}
                </View>
              </>
            )}
          </>
        )}
      </ScrollView>

      {/* Sticky summary bar, like a shopping cart */}
      {selected.length > 0 && (
        <View style={{ position: "absolute", left: 0, right: 0, bottom: 0, backgroundColor: colors.surface, borderTopWidth: 1, borderTopColor: colors.border, paddingHorizontal: 16, paddingTop: 12, paddingBottom: insets.bottom + 12, flexDirection: "row", alignItems: "center", gap: 14 }}>
          <View>
            <Text style={{ fontSize: 12, color: colors.textMuted }}>{selected.length} date{selected.length === 1 ? "" : "s"}</Text>
            <Text style={{ fontSize: 20, fontWeight: "800", color: colors.text }}>{total} <Text style={{ fontSize: 13, fontWeight: "600", color: colors.textMuted }}>bottles</Text></Text>
          </View>
          <Button title={allValid ? "Mark orders" : "Enter every count"} onPress={submit} disabled={!allValid} loading={mark.isPending} style={{ flex: 1, minHeight: 52 }} />
        </View>
      )}
    </KeyboardAvoidingView>
  );
}

function Shortcut({ label, onPress, tone = "brand" }: { label: string; onPress: () => void; tone?: "brand" | "plain" }) {
  return (
    <Pressable onPress={onPress} accessibilityRole="button" style={{ minHeight: 38, paddingHorizontal: 14, borderRadius: radius.pill, justifyContent: "center", backgroundColor: tone === "brand" ? colors.brand50 : colors.surface, borderWidth: 1, borderColor: tone === "brand" ? colors.brand200 : colors.border }}>
      <Text style={{ fontWeight: "700", fontSize: 13, color: tone === "brand" ? colors.brand700 : colors.textMuted }}>{label}</Text>
    </Pressable>
  );
}
