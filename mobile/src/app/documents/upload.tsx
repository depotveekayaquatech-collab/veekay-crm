import { useState } from "react";
import { Alert, Pressable, Text, View } from "react-native";
import { useRouter } from "expo-router";
import { api } from "@/api/api";
import { useWrite } from "@/api/hooks";
import { Button, Chips, ErrorNote, Screen, Title } from "@/components/ui";
import { PhotoField } from "@/components/PhotoField";
import { StorePicker } from "@/components/StorePicker";
import { appendFile, type Picked } from "@/lib/files";
import { recentMonths } from "@/lib/format";
import { colors, radius } from "@/theme";

const KINDS = [
  { label: "Payment proof", value: "payment" },
  { label: "Compliance card", value: "card" },
] as const;

export default function UploadDocument() {
  const router = useRouter();
  const months = recentMonths(12);
  const [store, setStore] = useState("");
  const [kind, setKind] = useState<"payment" | "card">("payment");
  const [month, setMonth] = useState(months[0].value);
  const [pickMonth, setPickMonth] = useState(false);
  const [files, setFiles] = useState<Picked[]>([]);
  const [error, setError] = useState<string | null>(null);
  const upload = useWrite((f: FormData) => api.uploadDocument(f), ["documents"]);

  function submit() {
    setError(null);
    const f = new FormData();
    f.append("store_id", store);
    f.append("kind", kind);
    f.append("month", month);
    files.forEach((p) => appendFile(f, "files", p));
    upload.mutate(f, {
      onSuccess: () => { Alert.alert("Uploaded", "Thank you. The document is on record."); router.back(); },
      onError: (e) => setError(e.message),
    });
  }

  return (
    <Screen keyboard>
      <Title sub="Several photos are joined into one PDF. Uploading again replaces the current file; the older one stays on record.">Upload a document</Title>
      <View style={{ gap: 18 }}>
        <StorePicker value={store} onChange={setStore} />
        <View style={{ gap: 8 }}>
          <Text style={{ fontSize: 13, fontWeight: "600", color: colors.text }}>Type</Text>
          <Chips options={[...KINDS]} value={kind} onChange={setKind} />
        </View>
        <View style={{ gap: 8 }}>
          <Text style={{ fontSize: 13, fontWeight: "600", color: colors.text }}>Month</Text>
          <Pressable onPress={() => setPickMonth((v) => !v)} accessibilityRole="button" style={{ minHeight: 52, borderRadius: radius.md, borderWidth: 1.5, borderColor: colors.border, backgroundColor: colors.surface, paddingHorizontal: 14, justifyContent: "center" }}>
            <Text style={{ fontSize: 16, color: colors.text }}>{months.find((m) => m.value === month)?.label}</Text>
          </Pressable>
          {pickMonth && (
            <View style={{ borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface, overflow: "hidden" }}>
              {months.map((m) => (
                <Pressable key={m.value} onPress={() => { setMonth(m.value); setPickMonth(false); }} accessibilityRole="button" style={{ minHeight: 48, paddingHorizontal: 14, justifyContent: "center", backgroundColor: m.value === month ? colors.brand50 : undefined }}>
                  <Text style={{ color: m.value === month ? colors.brand700 : colors.text, fontWeight: m.value === month ? "700" : "400" }}>{m.label}</Text>
                </Pressable>
              ))}
            </View>
          )}
        </View>
        <PhotoField files={files} onChange={setFiles} max={10} allowPdf label="Photos or a PDF" />
        {error ? <ErrorNote message={error} /> : null}
        <Button title="Upload" onPress={submit} loading={upload.isPending} disabled={!store || files.length === 0} />
      </View>
    </Screen>
  );
}
