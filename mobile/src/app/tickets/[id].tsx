import { useSubmissionKey } from "@/lib/submissionKey";
import { useState } from "react";
import { Alert, Pressable, Text, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useLocalSearchParams, useRouter } from "expo-router";
import { api, type Attachment } from "@/api/api";
import { useTicket, useWrite } from "@/api/hooks";
import { useAuth } from "@/auth/AuthProvider";
import { Button, Card, ErrorNote, Field, ListSkeleton, Screen, SectionTitle, TicketStatusBadge } from "@/components/ui";
import { PhotoField } from "@/components/PhotoField";
import { appendFile, openRemoteFile, type Picked } from "@/lib/files";
import { fmtDateTime, titleCase } from "@/lib/format";
import { colors, font, radius } from "@/theme";

function Photos({ ticketId, items }: { ticketId: string; items: Attachment[] }) {
  const [busy, setBusy] = useState<string | null>(null);
  if (!items.length) return null;
  return (
    <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 8, marginTop: 8 }}>
      {items.map((a, i) => (
        <Pressable
          key={a.id}
          disabled={busy === a.id}
          onPress={async () => {
            setBusy(a.id);
            try { await openRemoteFile(`/external/tickets/${ticketId}/attachments/${a.id}`, `ticket-photo-${i + 1}`); }
            catch (e) { Alert.alert("Couldn't open the photo", e instanceof Error ? e.message : "Please try again."); }
            finally { setBusy(null); }
          }}
          accessibilityRole="button"
          accessibilityLabel={`View photo ${i + 1}`}
          style={{ flexDirection: "row", alignItems: "center", gap: 6, minHeight: 44, paddingHorizontal: 12, borderRadius: radius.md, backgroundColor: colors.surfaceMuted }}
        >
          <Ionicons name="image-outline" size={16} color={colors.brand700} />
          <Text style={{ color: colors.brand700, fontWeight: "600", fontSize: 13 }}>{busy === a.id ? "Opening…" : `Photo ${i + 1}`}</Text>
        </Pressable>
      ))}
    </View>
  );
}

export default function TicketDetailScreen() {
  const { id = "" } = useLocalSearchParams<{ id: string }>();
  const { account } = useAuth();
  const router = useRouter();
  const isPoc = account?.kind === "poc";
  const q = useTicket(id);
  const [body, setBody] = useState("");
  const [photos, setPhotos] = useState<Picked[]>([]);
  const idem = useSubmissionKey();
  const reply = useWrite((f: FormData) => api.reply(id, f, idem.get()), ["ticket", "tickets"]);

  if (q.isLoading) return <Screen><ListSkeleton rows={3} /></Screen>;
  if (q.isError) return <Screen><ErrorNote message={q.error.message} onRetry={() => q.refetch()} /></Screen>;
  const t = q.data!;

  function send() {
    const f = new FormData();
    f.append("body", body.trim());
    photos.forEach((p) => appendFile(f, "photos", p));
    reply.mutate(f, {
      onSuccess: () => { idem.renew(); setBody(""); setPhotos([]); },
      onError: (e) => Alert.alert("Couldn't send", e.message),
    });
  }

  return (
    <Screen keyboard onRefresh={() => q.refetch()} refreshing={q.isRefetching}>
      <View style={{ flexDirection: "row", alignItems: "flex-start", justifyContent: "space-between", gap: 10 }}>
        <Text style={[font.title, { flex: 1, fontSize: 19 }]}>#{t.number} · {t.title}</Text>
        <TicketStatusBadge status={t.status} />
      </View>
      <Text style={[font.small, { marginTop: 6 }]}>{t.store_name} · {titleCase(t.category)} · raised {fmtDateTime(t.created_at)}</Text>
      {t.description ? <Card style={{ marginTop: 14 }}><Text style={{ color: colors.text, lineHeight: 22 }}>{t.description}</Text></Card> : null}
      <Photos ticketId={t.id} items={t.attachments.filter((a) => !a.comment_id)} />

      <SectionTitle>Conversation</SectionTitle>
      {t.comments.length === 0 && <Text style={font.small}>No replies yet.</Text>}
      <View style={{ gap: 10 }}>
        {t.comments.map((c) =>
          c.event ? (
            <Text key={c.id} style={[font.tiny, { textAlign: "center" }]}>{c.body} · {fmtDateTime(c.created_at)}</Text>
          ) : (
            <View key={c.id} style={{ maxWidth: "88%", alignSelf: c.mine ? "flex-end" : "flex-start", padding: 12, borderRadius: radius.lg, backgroundColor: c.mine ? colors.brand50 : colors.surface, borderWidth: c.mine ? 0 : 1, borderColor: colors.border }}>
              <Text style={[font.tiny, { fontWeight: "700", marginBottom: 3 }]}>{c.mine ? "You" : "Veekay team"} · {fmtDateTime(c.created_at)}</Text>
              <Text style={{ color: colors.text, lineHeight: 21 }}>{c.body}</Text>
              <Photos ticketId={t.id} items={t.attachments.filter((a) => a.comment_id === c.id)} />
            </View>
          ),
        )}
      </View>

      {!isPoc ? (
        <View style={{ marginTop: 20, padding: 14, borderRadius: radius.md, backgroundColor: colors.surfaceMuted }}>
          <Text style={{ color: colors.textMuted, lineHeight: 20 }}>Your store POC handles replies on this ticket. You will get an alert when it changes.</Text>
        </View>
      ) : t.status === "CLOSED" ? (
        <View style={{ marginTop: 20, padding: 14, borderRadius: radius.md, backgroundColor: colors.surfaceMuted, gap: 10 }}>
          <Text style={{ color: colors.textMuted }}>This ticket is closed.</Text>
          <Button title="Raise a new ticket" variant="secondary" onPress={() => router.push("/tickets/new")} />
        </View>
      ) : (
        <View style={{ marginTop: 20, gap: 14 }}>
          <Field label="Reply" value={body} onChangeText={setBody} multiline maxLength={2000} placeholder="Write a reply…" />
          <PhotoField files={photos} onChange={setPhotos} label="Add photos" />
          <Button title="Send reply" onPress={send} loading={reply.isPending} disabled={!body.trim()} />
        </View>
      )}
    </Screen>
  );
}
