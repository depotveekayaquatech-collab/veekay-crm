import { useMemo, useState } from "react";
import { Alert, KeyboardAvoidingView, Platform, Pressable, ScrollView, Text, TextInput, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { Stack, useLocalSearchParams, useRouter } from "expo-router";
import * as Haptics from "expo-haptics";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useCalendar, useCorrectEntry, useMarkMany, useMyStores } from "@/api/staffHooks";
import { useAuth } from "@/auth/AuthProvider";
import { useSubmissionKey } from "@/lib/submissionKey";
import { Button, Card, Chips, ErrorNote, ListSkeleton } from "@/components/ui";
import { MonthGrid, type CellState } from "@/components/MonthGrid";
import { daysAgo, fmtDate, fmtNumber } from "@/lib/format";
import { colors, font, radius } from "@/theme";

const MAX = 300;

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
  const { storeId, day, month } = useLocalSearchParams<{ storeId: string; day?: string; month?: string }>();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const mark = useMarkMany();
  const correct = useCorrectEntry();
  const { staff } = useAuth();
  const canFixOwn = !!staff?.can_correct_own_entries;       // off by default: a saved entry is corrected by a Team Lead or an admin
  // One key per submission: it stays the same while the person retries after a timeout, so the server answers from what it already saved.
  const submissionKey = useSubmissionKey();
  // The server's confirmation of the last submission. Nothing is called "saved" until the server says so.
  const [confirmed, setConfirmed] = useState<{ dates: number; bottles: number; at: string | null; repeated: number } | null>(null);
  const [notSaved, setNotSaved] = useState<string | null>(null);   // the request failed: the numbers below were NOT confirmed saved
  const [fixing, setFixing] = useState<string | null>(null);      // a day already marked that the employee is correcting
  const [fixValue, setFixValue] = useState("");
  const mine = useMyStores();
  const totals = mine.data?.find((s) => s.id === storeId);
  // Last month stays open for entries for the first few days of a month: the store list says so (and until when)
  const lastOpenUntil = totals?.last_month_open_until ?? null;
  const [period, setPeriod] = useState<"this" | "last">(month === "last" ? "last" : "this");
  const viewingLast = period === "last" && !!lastOpenUntil && !!totals;
  const lastYm = useMemo(() => {
    if (!totals) return undefined;
    const [y, m] = totals.today.split("-").map(Number);
    return m === 1 ? { year: y - 1, month: 12 } : { year: y, month: m - 1 };
  }, [totals]);
  const cal = useCalendar(storeId, viewingLast ? lastYm : undefined);
  const [picked, setPicked] = useState<string[] | null>(null);
  const [values, setValues] = useState<Record<string, string>>({});
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [same, setSame] = useState("");

  function switchPeriod(next: "this" | "last") {
    setPeriod(next);
    setPicked(null);
    setValues({});
    setErrors({});
  }

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

  /** Tapping a green (already marked) day opens a correction box for it; only the person who marked a day can change it. */
  function openFix(iso: string) {
    const d = byDate.get(iso);
    if (!d || !d.marked) return;
    Haptics.selectionAsync().catch(() => undefined);
    if (d.masked) {
      Alert.alert("Already marked by a colleague", "Someone else marked this day. You can't see or change their number. If it looks wrong, tell your Team Lead.");
      return;
    }
    if (!canFixOwn) {
      Alert.alert(
        "Saved on the server",
        `You marked ${d.count ?? 0} bottles${d.entered_at ? ` on ${new Date(d.entered_at).toLocaleString("en-IN", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}` : ""}. A saved entry can't be changed from the app. If it is wrong, ask your Team Lead or an admin to correct it; your original number stays in the history.`,
      );
      return;
    }
    if (d.source !== "employee") {
      Alert.alert(
        "Only an admin can change this day",
        `It was entered by ${d.entered_by ?? "an admin"}${d.entered_at ? ` on ${new Date(d.entered_at).toLocaleDateString("en-IN", { day: "numeric", month: "short" })}` : ""}, not by an employee, so an admin has to correct it. If it is wrong, tell your admin.`,
      );
      return;
    }
    setPicked([]);
    setFixing(iso);
    setFixValue(String(d.count ?? ""));
  }

  function saveFix(clear: boolean) {
    if (!fixing || (!clear && !valid(fixValue))) return;
    const run = () =>
      correct.mutate(
        { store_id: storeId, order_date: fixing, bottle_count: clear ? null : Number(fixValue) },
        {
          onSuccess: () => {
            Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success).catch(() => undefined);
            setFixing(null);
          },
          onError: (e) => Alert.alert("Couldn't change that", e.message),
        },
      );
    if (clear) Alert.alert(`Remove the entry for ${dayLabel(fixing)}?`, "The day becomes unmarked and you can mark it again.", [{ text: "Keep it", style: "cancel" }, { text: "Remove", style: "destructive", onPress: run }]);
    else run();
  }

  function toggle(iso: string) {
    if (byDate.get(iso)?.marked) return openFix(iso);
    setFixing(null);
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
    setNotSaved(null);
    Alert.alert(
      `Mark ${selected.length} date${selected.length === 1 ? "" : "s"}?`,
      `${total} bottles in total. If you get one wrong, tap that date afterwards to correct it.`,
      [
        { text: "Review", style: "cancel" },
        {
          text: "Mark orders",
          onPress: () => send(),
        },
      ],
    );
  }

  /** Send the selected dates. A retry after a failure reuses the same key, so the server never saves a second copy. */
  function send() {
    setNotSaved(null);
    setConfirmed(null);
    const sentTotal = total;
    mark.mutate(
      { store_id: storeId, key: submissionKey.get(), entries: selected.map((d) => ({ order_date: d, bottle_count: Number(values[d]) })) },
      {
        onSuccess: (r) => {
          const stored = r.results.filter((x) => x.ok && x.status);           // only what the server confirmed
          const failed = r.results.filter((x) => !x.ok);
          const done = new Set(stored.map((x) => x.order_date));
          setSelected((s) => s.filter((d) => !done.has(d)));
          setErrors(Object.fromEntries(failed.map((x) => [x.order_date, x.error ?? "Not saved"])));
          if (stored.length > 0) {
            Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success).catch(() => undefined);
            const times = stored.map((x) => x.saved_at).filter(Boolean).sort();
            setConfirmed({ dates: stored.length, bottles: failed.length ? 0 : sentTotal, at: times[0] ?? null, repeated: stored.filter((x) => x.status === "already_saved").length });
          }
          if (failed.length === 0) submissionKey.renew();
          else {
            Haptics.notificationAsync(Haptics.NotificationFeedbackType.Warning).catch(() => undefined);
            Alert.alert(`${stored.length} saved, ${failed.length} not saved`, "The dates that were not saved are still selected, with the reason shown. A colleague may already have marked them.");
          }
        },
        // The request failed or timed out: the server may or may not have it. Nothing is confirmed, the numbers stay here, and the retry is safe.
        onError: (e) => setNotSaved(e.message || "Couldn't reach the server."),
      },
    );
  }

  const state = (iso: string): CellState => {
    const d = byDate.get(iso);
    if (!d) return { disabled: true };
    return {
      disabled: d.is_future || cal.data?.can_mark === false,
      selected: selected.includes(iso) || fixing === iso,
      today: d.is_today,
      badge: d.masked ? "•" : d.marked ? d.count : null,
      badgeTone: d.masked ? "muted" : "done",
    };
  };

  return (
    <KeyboardAvoidingView style={{ flex: 1, backgroundColor: colors.surfaceSubtle }} behavior={Platform.OS === "ios" ? "padding" : undefined}>
      <Stack.Screen options={{ title: cal.data?.store_name ?? "Mark orders" }} />
      <ScrollView keyboardShouldPersistTaps="handled" contentContainerStyle={{ padding: 16, paddingBottom: 140 }}>
        {cal.isLoading ? <ListSkeleton rows={4} /> : cal.isError ? <ErrorNote message={cal.error.message} onRetry={() => cal.refetch()} /> : (
          <>
            <Text style={font.small}>{cal.data!.store_code}{totals?.crm_code ? ` · ${totals.crm_code}` : ""} · {cal.data!.month_label}</Text>
            {totals?.duplicate_name ? (
              <View style={{ marginTop: 8, padding: 12, borderRadius: radius.md, backgroundColor: colors.dangerSoft }}>
                <Text style={{ color: colors.danger, fontWeight: "800" }}>This store is listed twice in the CRM</Text>
                <Text style={[font.small, { marginTop: 2 }]}>Another store has exactly this name, so your entries may not show on the other copy. Tell your admin before you keep marking it.</Text>
              </View>
            ) : null}
            <Text style={[font.small, { marginTop: 2 }]}>Tap the dates to mark. {canFixOwn ? "Tap a green number to correct what you marked." : "A green number is saved on the server; a dot means a colleague marked that day."}</Text>
            {lastOpenUntil ? (
              <View style={{ marginTop: 12, gap: 8 }}>
                <Chips<"this" | "last"> options={[{ label: "This month", value: "this" }, { label: "Last month", value: "last" }]} value={period} onChange={switchPeriod} />
                {viewingLast ? (
                  <View style={{ padding: 12, borderRadius: radius.md, backgroundColor: colors.warningSoft }}>
                    <Text style={{ color: colors.warning, fontWeight: "700" }}>Last month is open for entries until {fmtDate(lastOpenUntil)}. After that only an admin can add them.</Text>
                  </View>
                ) : null}
              </View>
            ) : null}
            {cal.data?.can_mark === false ? (
              <View style={{ marginTop: 12, padding: 12, borderRadius: radius.md, backgroundColor: colors.surfaceMuted }}>
                <Text style={{ color: colors.textMuted, fontWeight: "600" }}>This month can't be changed here. Ask an admin to add or correct entries.</Text>
              </View>
            ) : null}
            {totals ? (
              <View style={{ flexDirection: "row", gap: 10, marginTop: 12 }}>
                {([["This month", totals.month_bottles ?? 0], ["Last month", totals.last_month_bottles ?? 0]] as const).map(([label, n]) => (
                  <View key={label} style={{ flex: 1, backgroundColor: colors.surface, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, paddingVertical: 10, paddingHorizontal: 12 }}>
                    <Text style={font.tiny}>You marked {label.toLowerCase()}</Text>
                    <Text style={{ fontSize: 22, fontWeight: "800", color: colors.text }}>{fmtNumber(n)}<Text style={{ fontSize: 12, fontWeight: "600", color: colors.textMuted }}> bottles</Text></Text>
                  </View>
                ))}
              </View>
            ) : null}

            <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 8, marginTop: 14 }}>
              {today && !byDate.get(today)?.marked ? <Shortcut label="Today" onPress={() => add([today])} /> : null}
              {byDate.get(yesterday) && !byDate.get(yesterday)!.marked ? <Shortcut label="Yesterday" onPress={() => add([yesterday])} /> : null}
              {open.length > 1 ? <Shortcut label={`All ${open.length} unmarked days`} onPress={() => add(open)} /> : null}
              {selected.length > 0 ? <Shortcut label="Clear" tone="plain" onPress={() => setSelected([])} /> : null}
            </View>

            <Card style={{ marginTop: 14, padding: 8 }}>
              <MonthGrid year={cal.data!.year} month={cal.data!.month} state={state} onPress={toggle} />
            </Card>

            {fixing ? (
              <Card style={{ marginTop: 12, padding: 14, borderColor: colors.brand200, backgroundColor: colors.brand50 }}>
                <Text style={{ fontSize: 15, fontWeight: "800", color: colors.brand800 }}>Correct {dayLabel(fixing)}</Text>
                <Text style={[font.small, { marginTop: 2 }]}>Entered as {byDate.get(fixing)?.count ?? 0} bottles{byDate.get(fixing)?.entered_by ? ` by ${byDate.get(fixing)?.entered_by}` : ""}. What it should be:</Text>
                <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginTop: 10 }}>
                  <Stepper value={fixValue} onChange={setFixValue} error={fixValue !== "" && !valid(fixValue)} label={dayLabel(fixing)} />
                  <View style={{ flexDirection: "row", gap: 8 }}>
                    <Button title="Remove" variant="secondary" onPress={() => saveFix(true)} disabled={correct.isPending} style={{ minHeight: 44, paddingHorizontal: 14 }} />
                    <Button title="Save" onPress={() => saveFix(false)} disabled={!valid(fixValue) || correct.isPending} loading={correct.isPending} style={{ minHeight: 44, paddingHorizontal: 18 }} />
                  </View>
                </View>
                <Pressable onPress={() => setFixing(null)} accessibilityRole="button" style={{ marginTop: 10, minHeight: 36, justifyContent: "center" }}>
                  <Text style={{ color: colors.brand700, fontWeight: "700" }}>Cancel</Text>
                </Pressable>
              </Card>
            ) : null}

            {open.length === 0 ? (
              <View style={{ marginTop: 16, padding: 14, borderRadius: radius.md, backgroundColor: colors.successSoft }}>
                <Text style={{ color: colors.success, fontWeight: "700" }}>{viewingLast ? "Every date of last month is marked for this store." : "Every date up to today is marked for this store."}</Text>
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

      {/* What the server said about the last submission */}
      {mark.isPending ? (
        <View accessibilityRole="alert" style={{ position: "absolute", left: 0, right: 0, bottom: 0, backgroundColor: colors.surface, borderTopWidth: 1, borderTopColor: colors.border, paddingHorizontal: 16, paddingTop: 14, paddingBottom: insets.bottom + 14 }}>
          <Text style={{ fontWeight: "800", color: colors.text }}>Saving to the server…</Text>
          <Text style={font.small}>Please wait. Your numbers are not saved until this says so.</Text>
        </View>
      ) : notSaved ? (
        <View accessibilityRole="alert" style={{ position: "absolute", left: 0, right: 0, bottom: 0, backgroundColor: colors.dangerSoft, borderTopWidth: 1, borderTopColor: colors.danger, paddingHorizontal: 16, paddingTop: 14, paddingBottom: insets.bottom + 14, gap: 8 }}>
          <Text style={{ fontWeight: "800", color: colors.danger }}>NOT saved yet</Text>
          <Text style={font.small}>{notSaved} Your numbers are still on this screen. Tap Retry: it will not create duplicates, even if the first try did reach the server.</Text>
          <Button title="Retry" onPress={send} style={{ minHeight: 48 }} />
        </View>
      ) : confirmed && selected.length === 0 ? (
        <View accessibilityRole="alert" style={{ position: "absolute", left: 0, right: 0, bottom: 0, backgroundColor: colors.successSoft, borderTopWidth: 1, borderTopColor: colors.success, paddingHorizontal: 16, paddingTop: 14, paddingBottom: insets.bottom + 14, gap: 8 }}>
          <Text style={{ fontWeight: "800", color: colors.success }}>
            <Ionicons name="cloud-done-outline" size={16} color={colors.success} /> Saved on the server
          </Text>
          <Text style={font.small}>
            {confirmed.dates} date{confirmed.dates === 1 ? "" : "s"}{confirmed.bottles ? ` · ${confirmed.bottles} bottles` : ""}
            {confirmed.at ? ` · server time ${new Date(confirmed.at).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" })}` : ""}
            {confirmed.repeated ? `. ${confirmed.repeated} had already been saved by your earlier try, nothing was duplicated.` : "."}
          </Text>
          <Button title="Done" onPress={() => router.back()} style={{ minHeight: 48 }} />
        </View>
      ) : null}

      {/* Sticky summary bar, like a shopping cart */}
      {selected.length > 0 && !mark.isPending && !notSaved && (
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
