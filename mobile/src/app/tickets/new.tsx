import { useSubmissionKey } from "@/lib/submissionKey";
import { useState } from "react";
import { Alert, Pressable, Text, View } from "react-native";
import { Redirect, useRouter } from "expo-router";
import { api } from "@/api/api";
import { useWrite } from "@/api/hooks";
import { useAuth } from "@/auth/AuthProvider";
import { Button, ErrorNote, Field, Screen, Title } from "@/components/ui";
import { PhotoField } from "@/components/PhotoField";
import { StorePicker } from "@/components/StorePicker";
import { appendFile, type Picked } from "@/lib/files";
import { colors, radius } from "@/theme";

const CATEGORIES = [
  ["SHORT_SUPPLY", "Short supply"], ["LATE_DELIVERY", "Late delivery"], ["NO_DELIVERY", "No delivery"], ["DAMAGED", "Damaged bottles"],
  ["QUALITY", "Quality issue"], ["BILLING", "Billing"], ["OTHER", "Something else"],
] as const;

export default function NewTicket() {
  const { account } = useAuth();
  const router = useRouter();
  const [store, setStore] = useState("");
  const [category, setCategory] = useState<string>("SHORT_SUPPLY");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [photos, setPhotos] = useState<Picked[]>([]);
  const [error, setError] = useState<string | null>(null);
  const idem = useSubmissionKey();
  const raise = useWrite((f: FormData) => api.raiseTicket(f, idem.get()), ["tickets", "notifications"]);

  // Only a store POC raises tickets (the server enforces it too).
  if (account?.kind !== "poc") return <Redirect href="/tickets" />;

  function submit() {
    setError(null);
    const f = new FormData();
    f.append("store_id", store);
    f.append("category", category);
    f.append("title", title.trim());
    if (description.trim()) f.append("description", description.trim());
    photos.forEach((p) => appendFile(f, "photos", p));
    raise.mutate(f, {
      onSuccess: (t) => { idem.renew(); Alert.alert("Ticket raised", "Our team has been told and will get back to you."); router.replace(`/tickets/${t.id}`); },
      onError: (e) => setError(e.message),
    });
  }

  return (
    <Screen keyboard>
      <Title sub="Tell us what went wrong. Photos help us fix it faster.">Raise a ticket</Title>
      <View style={{ gap: 18 }}>
        <StorePicker value={store} onChange={setStore} />
        <View style={{ gap: 8 }}>
          <Text style={{ fontSize: 13, fontWeight: "600", color: colors.text }}>What happened?</Text>
          <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 8 }}>
            {CATEGORIES.map(([v, l]) => {
              const on = category === v;
              return (
                <Pressable key={v} onPress={() => setCategory(v)} accessibilityRole="radio" accessibilityState={{ selected: on }}
                  style={{ minHeight: 40, paddingHorizontal: 14, borderRadius: radius.pill, borderWidth: 1, borderColor: on ? colors.brand600 : colors.border, backgroundColor: on ? colors.brand50 : colors.surface, justifyContent: "center" }}>
                  <Text style={{ fontWeight: "600", color: on ? colors.brand700 : colors.textMuted }}>{l}</Text>
                </Pressable>
              );
            })}
          </View>
        </View>
        <Field label="Short title" value={title} onChangeText={setTitle} maxLength={160} placeholder="e.g. Only 40 of 100 bottles arrived" />
        <Field label="Details (optional)" value={description} onChangeText={setDescription} maxLength={2000} multiline />
        <PhotoField files={photos} onChange={setPhotos} />
        {error ? <ErrorNote message={error} /> : null}
        <Button title="Send ticket" onPress={submit} loading={raise.isPending} disabled={!store || title.trim().length < 3} />
      </View>
    </Screen>
  );
}
