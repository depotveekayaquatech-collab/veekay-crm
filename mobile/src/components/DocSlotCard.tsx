import { useState } from "react";
import { ActivityIndicator, Alert, Image, Modal, Pressable, ScrollView, Text, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { complianceApi, type DocBrief } from "@/api/complianceApi";
import { useDocFile, useDocVersions, useRefreshCompliance } from "@/api/complianceHooks";
import { Badge, Button, Card, ErrorNote } from "@/components/ui";
import { fmtBytes, KIND_LABEL, KIND_UPLOAD, monthLabel, slotBadge, type DocKind } from "@/lib/compliance";
import { fmtDate, fmtDateTime } from "@/lib/format";
import { colors, font, radius } from "@/theme";
import type { ViewerSource } from "@/components/AttachmentViewer";

const ICON: Record<DocKind, React.ComponentProps<typeof Ionicons>["name"]> = { card: "id-card-outline", bill: "receipt-outline", payment: "card-outline" };

interface Props {
  kind: DocKind;
  doc: DocBrief | null;
  month: string;
  /** Show a small picture of the current file (only fetched when this is set and the file is a photo). */
  preview?: boolean;
  onView: (v: ViewerSource) => void;
  onUpload: (kind: DocKind, replacing: boolean) => void;
}

export function DocSlotCard({ kind, doc, month, preview, onView, onUpload }: Props) {
  const [history, setHistory] = useState(false);
  const refresh = useRefreshCompliance();
  const [removing, setRemoving] = useState(false);
  const badge = slotBadge(kind, doc);
  const isImage = !!doc && doc.content_type.startsWith("image/");

  function remove() {
    if (!doc) return;
    Alert.alert(
      `Remove this ${KIND_LABEL[kind].toLowerCase()}?`,
      "It is hidden from the lists. The file itself stays stored, and uploading again brings it back.",
      [
        { text: "Keep it", style: "cancel" },
        {
          text: "Remove", style: "destructive",
          onPress: async () => {
            setRemoving(true);
            try { await complianceApi.remove(doc.id); await refresh(); }
            catch (e) { Alert.alert("Couldn't remove it", e instanceof Error ? e.message : "Please try again."); }
            finally { setRemoving(false); }
          },
        },
      ],
    );
  }

  return (
    <Card style={{ gap: 12 }}>
      <View style={{ flexDirection: "row", alignItems: "center", gap: 12 }}>
        <View style={{ width: 42, height: 42, borderRadius: 21, backgroundColor: doc ? colors.successSoft : colors.surfaceMuted, alignItems: "center", justifyContent: "center" }}>
          <Ionicons name={ICON[kind]} size={22} color={doc ? colors.success : colors.textMuted} />
        </View>
        <Text style={{ flex: 1, fontSize: 17, fontWeight: "800", color: colors.text }}>{KIND_LABEL[kind]}</Text>
        <Badge tone={badge.tone}>{badge.text}</Badge>
      </View>

      {doc ? (
        <>
          {preview && isImage ? <Thumb id={doc.id} title={KIND_LABEL[kind]} onView={onView} /> : null}
          <View style={{ gap: 2 }}>
            <Text numberOfLines={1} style={{ fontSize: 14, fontWeight: "600", color: colors.text }}>{doc.file_name}</Text>
            <Text style={font.small}>
              {fmtBytes(doc.size_bytes)} · {doc.content_type === "application/pdf" ? "PDF" : "Photo"}
            </Text>
            <Text style={font.small}>Uploaded {fmtDateTime(doc.uploaded_at)}{doc.uploaded_by ? ` by ${doc.uploaded_by}` : ""}</Text>
            {kind === "bill" && doc.due_date ? (
              <Text style={[font.small, doc.overdue && doc.status !== "CLEARED" ? { color: colors.danger, fontWeight: "700" } : null]}>Due {fmtDate(doc.due_date)}</Text>
            ) : null}
          </View>
          <View style={{ flexDirection: "row", gap: 10 }}>
            <Button title="View" variant="secondary" style={{ flex: 1 }} icon={<Ionicons name="eye-outline" size={20} color={colors.brand700} />}
              onPress={() => onView({ kind: "stored", id: doc.id, title: `${KIND_LABEL[kind]} · ${monthLabel(month)}` })} />
            <Button title="Upload new" style={{ flex: 1 }} icon={<Ionicons name="cloud-upload-outline" size={20} color={colors.white} />} onPress={() => onUpload(kind, true)} />
          </View>
          <View style={{ flexDirection: "row", gap: 8 }}>
            <TextButton icon="time-outline" label="History" onPress={() => setHistory(true)} />
            <TextButton icon="trash-outline" label={removing ? "Removing…" : "Remove"} tone="danger" disabled={removing} onPress={remove} />
          </View>
        </>
      ) : (
        <>
          <Text style={font.small}>Nothing uploaded for {monthLabel(month)}.</Text>
          <Button title={KIND_UPLOAD[kind]} icon={<Ionicons name="camera-outline" size={20} color={colors.white} />} onPress={() => onUpload(kind, false)} />
        </>
      )}

      {history && doc ? <HistorySheet doc={doc} kind={kind} month={month} onView={(v) => { setHistory(false); onView(v); }} onClose={() => setHistory(false)} /> : null}
    </Card>
  );
}

function TextButton({ icon, label, onPress, tone, disabled }: { icon: React.ComponentProps<typeof Ionicons>["name"]; label: string; onPress: () => void; tone?: "danger"; disabled?: boolean }) {
  const color = tone === "danger" ? colors.danger : colors.brand600;
  return (
    <Pressable onPress={onPress} disabled={disabled} accessibilityRole="button" hitSlop={6}
      style={{ minHeight: 44, paddingHorizontal: 12, flexDirection: "row", alignItems: "center", gap: 6, opacity: disabled ? 0.5 : 1 }}>
      <Ionicons name={icon} size={18} color={color} />
      <Text style={{ fontWeight: "700", color }}>{label}</Text>
    </Pressable>
  );
}

/** A picture of the current photo. It asks for the file only when it is shown. */
function Thumb({ id, title, onView }: { id: string; title: string; onView: (v: ViewerSource) => void }) {
  const file = useDocFile(id, undefined, true);
  const [broken, setBroken] = useState(false);
  const box = { height: 160, borderRadius: radius.md, overflow: "hidden" as const, backgroundColor: colors.surfaceMuted, alignItems: "center" as const, justifyContent: "center" as const };
  if (file.error || broken) return <View style={box}><Text style={font.small}>Preview unavailable. Tap View.</Text></View>;
  if (!file.uri) return <View style={box}><ActivityIndicator color={colors.brand600} /></View>;
  return (
    <Pressable onPress={() => onView({ kind: "stored", id, title })} accessibilityRole="imagebutton" accessibilityLabel={`${title}. Tap to see it larger.`} style={box}>
      <Image source={{ uri: file.uri }} resizeMode="cover" onError={() => setBroken(true)} style={{ width: "100%", height: "100%" }} />
    </Pressable>
  );
}

function HistorySheet({ doc, kind, month, onView, onClose }: { doc: DocBrief; kind: DocKind; month: string; onView: (v: ViewerSource) => void; onClose: () => void }) {
  const insets = useSafeAreaInsets();
  const q = useDocVersions(doc.id);
  return (
    <Modal visible animationType="slide" onRequestClose={onClose} statusBarTranslucent>
      <View style={{ flex: 1, backgroundColor: colors.surfaceSubtle, paddingTop: insets.top }}>
        <View style={{ flexDirection: "row", alignItems: "center", padding: 16, backgroundColor: colors.surface, borderBottomWidth: 1, borderBottomColor: colors.border }}>
          <View style={{ flex: 1 }}>
            <Text style={{ fontSize: 18, fontWeight: "800", color: colors.text }}>{KIND_LABEL[kind]} history</Text>
            <Text style={font.small}>{monthLabel(month)} · every file ever uploaded is kept</Text>
          </View>
          <Pressable onPress={onClose} accessibilityRole="button" accessibilityLabel="Close" hitSlop={12} style={{ width: 44, height: 44, alignItems: "center", justifyContent: "center" }}>
            <Ionicons name="close" size={26} color={colors.text} />
          </Pressable>
        </View>
        <ScrollView contentContainerStyle={{ padding: 16, gap: 10, paddingBottom: 24 + insets.bottom }}>
          {q.isLoading ? <ActivityIndicator color={colors.brand600} /> : q.isError ? <ErrorNote message={q.error.message} onRetry={() => q.refetch()} /> : (q.data ?? []).map((v) => (
            <Card key={v.version} onPress={() => onView({ kind: "stored", id: doc.id, version: v.version, title: `${KIND_LABEL[kind]} · version ${v.version}` })} label={`Open version ${v.version}`} style={{ gap: 4 }}>
              <View style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
                <Text style={{ fontSize: 16, fontWeight: "800", color: colors.text }}>Version {v.version}</Text>
                {v.current ? <Badge tone="success">Current</Badge> : null}
                {v.source_files > 1 ? <Badge tone="info">{v.source_files} photos merged</Badge> : null}
              </View>
              <Text style={font.small}>{fmtDateTime(v.uploaded_at)} · {fmtBytes(v.size_bytes)} · {v.content_type === "application/pdf" ? "PDF" : "Photo"}</Text>
            </Card>
          ))}
        </ScrollView>
      </View>
    </Modal>
  );
}
