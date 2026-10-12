import { useState } from "react";
import { Alert, Pressable, Text, View } from "react-native";
import { Redirect, useRouter } from "expo-router";
import { api, type Outcome } from "@/api/api";
import { useWrite } from "@/api/hooks";
import { useAuth } from "@/auth/AuthProvider";
import { Button, Chips, ErrorNote, Field, Screen, Title } from "@/components/ui";
import { PhotoField } from "@/components/PhotoField";
import { StorePicker } from "@/components/StorePicker";
import { appendFile, type Picked } from "@/lib/files";
import { daysAgo, fmtDate } from "@/lib/format";
import { colors, radius } from "@/theme";

const OUTCOMES: { value: Outcome; label: string; hint: string }[] = [
  { value: "RECEIVED", label: "All received", hint: "Everything arrived fine" },
  { value: "SHORT", label: "Short", hint: "Fewer bottles than expected" },
  { value: "DAMAGED", label: "Damaged", hint: "Bottles arrived damaged" },
];

// The server accepts the last 14 days.
const DAYS = Array.from({ length: 15 }, (_, i) => ({
  value: daysAgo(i),
  label: i === 0 ? "Today" : i === 1 ? "Yesterday" : fmtDate(daysAgo(i)).replace(/ \d{4}$/, ""),
}));

export default function ConfirmDelivery() {
  const { account } = useAuth();
  const router = useRouter();
  const [store, setStore] = useState("");
  const [date, setDate] = useState(DAYS[0].value);
  const [outcome, setOutcome] = useState<Outcome>("RECEIVED");
  const [expected, setExpected] = useState("");
  const [received, setReceived] = useState("");
  const [note, setNote] = useState("");
  const [photos, setPhotos] = useState<Picked[]>([]);
  const [error, setError] = useState<string | null>(null);
  const confirm = useWrite((f: FormData) => api.confirmDelivery(f), ["deliveries", "tickets"]);
  const problem = outcome !== "RECEIVED";

  if (account?.kind !== "poc") return <Redirect href="/deliveries" />;

  function submit() {
    setError(null);
    const f = new FormData();
    f.append("store_id", store);
    f.append("delivery_date", date);
    f.append("outcome", outcome);
    if (problem) {
      if (expected) f.append("expected_qty", expected);
      if (received) f.append("received_qty", received);
      if (note.trim()) f.append("note", note.trim());
      photos.forEach((p) => appendFile(f, "photos", p));
    }
    confirm.mutate(f, {
      onSuccess: (d) => {
        Alert.alert(d.ticket_id ? "Reported" : "Thank you", d.ticket_id ? "A ticket was opened for our team." : "Delivery confirmed.");
        router.back();
      },
      onError: (e) => setError(e.message),
    });
  }

  return (
    <Screen keyboard>
      <Title sub="Once per store per day. Short or damaged deliveries open a ticket for our team.">Confirm a delivery</Title>
      <View style={{ gap: 18 }}>
        <StorePicker value={store} onChange={setStore} />
        <View style={{ gap: 8 }}>
          <Text style={{ fontSize: 13, fontWeight: "600", color: colors.text }}>Delivery date</Text>
          <Chips options={DAYS} value={date} onChange={setDate} />
        </View>
        <View style={{ gap: 8 }} accessibilityRole="radiogroup">
          <Text style={{ fontSize: 13, fontWeight: "600", color: colors.text }}>How did it go?</Text>
          {OUTCOMES.map((o) => {
            const on = outcome === o.value;
            return (
              <Pressable key={o.value} onPress={() => setOutcome(o.value)} accessibilityRole="radio" accessibilityState={{ selected: on }}
                style={{ padding: 14, borderRadius: radius.md, borderWidth: 1.5, borderColor: on ? colors.brand600 : colors.border, backgroundColor: on ? colors.brand50 : colors.surface }}>
                <Text style={{ fontSize: 15, fontWeight: "700", color: colors.text }}>{o.label}</Text>
                <Text style={{ color: colors.textMuted, fontSize: 13 }}>{o.hint}</Text>
              </Pressable>
            );
          })}
        </View>
        {problem && (
          <>
            <View style={{ flexDirection: "row", gap: 12 }}>
              <View style={{ flex: 1 }}><Field label="Expected" value={expected} onChangeText={(v) => setExpected(v.replace(/\D/g, ""))} keyboardType="number-pad" maxLength={6} /></View>
              <View style={{ flex: 1 }}><Field label="Received" value={received} onChangeText={(v) => setReceived(v.replace(/\D/g, ""))} keyboardType="number-pad" maxLength={6} /></View>
            </View>
            <Field label="What was wrong?" value={note} onChangeText={setNote} multiline maxLength={1000} />
            <PhotoField files={photos} onChange={setPhotos} />
          </>
        )}
        {error ? <ErrorNote message={error} /> : null}
        <Button title={problem ? "Report problem" : "Confirm delivery"} onPress={submit} loading={confirm.isPending} disabled={!store || (problem && !note.trim() && !received)} />
      </View>
    </Screen>
  );
}
