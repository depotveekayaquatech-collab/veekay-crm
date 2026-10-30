import { useSubmissionKey } from "@/lib/submissionKey";
import { useState } from "react";
import { Alert, Pressable, Text, TextInput, View } from "react-native";
import { useRouter } from "expo-router";
import { ApiError } from "@/api/client";
import { staffApi, type DuplicateAnswer } from "@/api/staff";
import { useCashOptions, useStaffWrite } from "@/api/staffHooks";
import { Button, Chips, ErrorNote, Field, Screen } from "@/components/ui";
import { PhotoField } from "@/components/PhotoField";
import { StorePicker } from "@/components/StorePicker";
import { appendFile, type Picked } from "@/lib/files";
import { daysAgo, fmtDate } from "@/lib/format";
import { colors, radius } from "@/theme";

const DAYS = Array.from({ length: 8 }, (_, i) => ({ value: daysAgo(i), label: i === 0 ? "Today" : i === 1 ? "Yesterday" : fmtDate(daysAgo(i)).replace(/ \d{4}$/, "") }));

/** Amount first, then the details, then the bill photo: the order expense apps use. */
export default function NewExpense() {
  const router = useRouter();
  const opts = useCashOptions();
  const [kind, setKind] = useState<"OFFICE" | "STORE">("OFFICE");
  const [amount, setAmount] = useState("");
  const [category, setCategory] = useState("");
  const [store, setStore] = useState("");
  const [date, setDate] = useState(DAYS[0].value);
  const [other, setOther] = useState("");
  const [notes, setNotes] = useState("");
  const [proof, setProof] = useState<Picked[]>([]);
  const [error, setError] = useState<string | null>(null);
  const idem = useSubmissionKey();
  const add = useStaffWrite((f: FormData) => staffApi.addCash(f, idem.get()), ["s-cash"]);

  const reasons = (kind === "OFFICE" ? opts.data?.office_reasons : opts.data?.store_reasons) ?? [];
  const max = Number(opts.data?.max_amount ?? 0);
  const amt = /^\d+(\.\d{1,2})?$/.test(amount) ? Number(amount) : null;
  const needsOther = category.toUpperCase() === "OTHER";
  const problem =
    amt === null || amt <= 0 ? "Enter the amount" : max && amt > max ? `The most you can enter is ₹${max.toLocaleString("en-IN")}` :
    !category ? "Choose what it was for" : kind === "STORE" && !store ? "Choose the store" : needsOther && !other.trim() ? "Say what it was for" : proof.length === 0 ? "Attach a photo of the bill" : null;

  /** The server says this looks like a purchase already recorded: show it and let the person decide. Nothing is saved until they do. */
  function askAboutDuplicate(d: DuplicateAnswer) {
    const m = d.matches[0];
    const line = `${fmtDate(m.purchase_date)} · ₹${Number(m.amount).toLocaleString("en-IN")} · ${m.store_name ?? "Office"} · ${m.category_label}\nRecorded by ${m.added_by} on ${fmtDate(m.created_at)}${m.same_file ? "\nThe same bill photo" : ""}`;
    Alert.alert(
      "Is this the same purchase?",
      `${d.message}\n\n${line}${d.matches.length > 1 ? `\n(and ${d.matches.length - 1} more like it)` : ""}`,
      [
        { text: "It is the same: don't save", style: "cancel", onPress: () => router.back() },
        { text: "It is different: save it", onPress: () => submit(true) },
      ],
      { cancelable: false },
    );
  }

  function submit(confirmDuplicate = false) {
    setError(null);
    const f = new FormData();
    f.append("kind", kind);
    f.append("purchase_date", date);
    f.append("category", category);
    f.append("amount", amount);
    if (kind === "STORE") f.append("store_id", store);
    if (needsOther) f.append("other_reason", other.trim());
    if (confirmDuplicate) f.append("confirm_duplicate", "true");
    if (notes.trim()) f.append("notes", notes.trim());
    appendFile(f, "proof", proof[0]);
    add.mutate(f, {
      onSuccess: () => { idem.renew(); Alert.alert("Saved", "Your purchase was recorded."); router.back(); },
      onError: (e) => {
        const b = e instanceof ApiError && e.status === 409 ? (e.body as { code?: string; detail?: string; matches?: DuplicateAnswer["matches"] } | undefined) : undefined;
        if (b && b.code === "POSSIBLE_DUPLICATE" && b.matches?.length) askAboutDuplicate({ code: "POSSIBLE_DUPLICATE", message: b.detail ?? "", matches: b.matches });
        else setError(e.message);
      },
    });
  }

  return (
    <Screen keyboard>
      <View style={{ alignItems: "center", paddingVertical: 18 }}>
        <Text style={{ fontSize: 13, color: colors.textMuted, fontWeight: "600" }}>AMOUNT</Text>
        <View style={{ flexDirection: "row", alignItems: "center", marginTop: 6 }}>
          <Text style={{ fontSize: 40, fontWeight: "800", color: colors.textFaint }}>₹</Text>
          <TextInput
            value={amount}
            onChangeText={(t) => setAmount(t.replace(/[^\d.]/g, "").replace(/(\..*)\./g, "$1"))}
            keyboardType="decimal-pad"
            placeholder="0"
            placeholderTextColor={colors.border}
            accessibilityLabel="Amount in rupees"
            autoFocus
            maxLength={9}
            style={{ minWidth: 100, fontSize: 52, fontWeight: "800", color: colors.text, textAlign: "center", padding: 0 }}
          />
        </View>
      </View>

      <View style={{ gap: 18 }}>
        <View style={{ flexDirection: "row", backgroundColor: colors.surfaceMuted, borderRadius: radius.pill, padding: 4 }}>
          {(["OFFICE", "STORE"] as const).map((k) => (
            <Pressable key={k} onPress={() => { setKind(k); setCategory(""); }} accessibilityRole="button" accessibilityState={{ selected: kind === k }}
              style={{ flex: 1, height: 44, borderRadius: radius.pill, alignItems: "center", justifyContent: "center", backgroundColor: kind === k ? colors.surface : "transparent" }}>
              <Text style={{ fontWeight: "800", color: kind === k ? colors.brand700 : colors.textMuted }}>{k === "OFFICE" ? "Office" : "A store"}</Text>
            </Pressable>
          ))}
        </View>

        {kind === "STORE" && <StorePicker value={store} onChange={setStore} stores={opts.data?.stores ?? []} />}

        <View style={{ gap: 8 }}>
          <Text style={{ fontSize: 13, fontWeight: "600", color: colors.text }}>What was it for?</Text>
          <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 8 }}>
            {reasons.map((r) => {
              const on = category === r.code;
              return (
                <Pressable key={r.code} onPress={() => setCategory(r.code)} accessibilityRole="radio" accessibilityState={{ selected: on }}
                  style={{ minHeight: 44, paddingHorizontal: 14, borderRadius: radius.pill, borderWidth: 1, borderColor: on ? colors.brand600 : colors.border, backgroundColor: on ? colors.brand50 : colors.surface, justifyContent: "center" }}>
                  <Text style={{ fontWeight: "600", color: on ? colors.brand700 : colors.textMuted }}>{r.label}</Text>
                </Pressable>
              );
            })}
          </View>
        </View>
        {needsOther && <Field label="Reason" value={other} onChangeText={setOther} maxLength={120} />}

        <View style={{ gap: 8 }}>
          <Text style={{ fontSize: 13, fontWeight: "600", color: colors.text }}>Date</Text>
          <Chips options={DAYS} value={date} onChange={setDate} />
        </View>

        <PhotoField files={proof} onChange={setProof} max={1} allowPdf label="Photo of the bill" />
        <Field label="Notes (optional)" value={notes} onChangeText={setNotes} multiline maxLength={500} />

        {error ? <ErrorNote message={error} /> : null}
        {problem && amount ? <Text style={{ color: colors.textMuted, fontSize: 13 }}>{problem}</Text> : null}
        <Button title="Save purchase" onPress={() => submit()} loading={add.isPending} disabled={!!problem} />
      </View>
    </Screen>
  );
}
