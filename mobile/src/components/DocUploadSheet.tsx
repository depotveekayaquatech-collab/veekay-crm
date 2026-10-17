import { useRef, useState } from "react";
import { Alert, Image, Modal, Pressable, ScrollView, Text, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import * as Haptics from "expo-haptics";
import { randomUUID } from "expo-crypto";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { complianceApi } from "@/api/complianceApi";
import { useRefreshCompliance, useUploadPolicy } from "@/api/complianceHooks";
import { AttachmentViewer, type ViewerSource } from "@/components/AttachmentViewer";
import { Button, ProgressBar } from "@/components/ui";
import { describeSelection, fmtBytes, isPdf, KIND_LABEL, KIND_UPLOAD, monthLabel, selectionSignature, validateSelection, type DocKind } from "@/lib/compliance";
import { appendFile, pickPdf, pickPhotos, takePhoto, type Picked } from "@/lib/files";
import { shrinkForUpload } from "@/lib/imagePrep";
import { colors, font, radius } from "@/theme";

type Phase = "idle" | "preparing" | "uploading" | "done";

interface Props {
  store: { id: string; name: string; code: string };
  month: string;
  kind: DocKind;
  /** The slot already has a file: the new one becomes the current one and the earlier one stays in the history. */
  replacing: boolean;
  onClose: () => void;
}

/**
 * Add a card, invoice or payment proof for one store and month. The same route and rules as the web page: one photo is saved
 * (shrunk), several photos are merged into one PDF, a PDF goes alone. Nothing is "saved" until the server says so, and a retry of
 * the same selection reuses its Idempotency-Key, so it can never create a second version.
 */
export function DocUploadSheet({ store, month, kind, replacing, onClose }: Props) {
  const insets = useSafeAreaInsets();
  const policy = useUploadPolicy();
  const refresh = useRefreshCompliance();
  const [files, setFiles] = useState<Picked[]>([]);
  const [phase, setPhase] = useState<Phase>("idle");
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [view, setView] = useState<ViewerSource | null>(null);
  const abort = useRef<AbortController | null>(null);
  const key = useRef<{ sig: string; id: string } | null>(null);

  const busy = phase === "preparing" || phase === "uploading";
  const problem = validateSelection(files, policy);
  const canSend = files.length > 0 && !problem && !busy && phase !== "done";
  const hasPdf = files.some(isPdf);

  async function add(getPicked: () => Promise<Picked[]>) {
    if (busy) return;
    setError(null);
    const picked = await getPicked();
    if (picked.length === 0) return;
    setPhase("preparing");
    const prepared: Picked[] = [];
    for (const p of picked) prepared.push(await shrinkForUpload(p, policy));      // a photo is shrunk here; a PDF is left as it is
    setFiles((prev) => [...prev, ...prepared]);
    setPhase("idle");
  }

  async function send() {
    if (!canSend) return;
    setError(null);
    setProgress(0);
    setPhase("uploading");
    const sig = selectionSignature(files);
    if (key.current?.sig !== sig) key.current = { sig, id: randomUUID() };          // a new selection is a new submission; a retry is not
    const form = new FormData();
    form.append("store_id", store.id);
    form.append("month", month);
    form.append("kind", kind);
    files.forEach((f) => appendFile(form, "files", f));
    const ctl = new AbortController();
    abort.current = ctl;
    try {
      await complianceApi.upload(form, { idempotencyKey: key.current.id, onProgress: setProgress, signal: ctl.signal });
      key.current = null;
      await refresh();
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success).catch(() => undefined);
      setPhase("done");                                                             // only now: the server stored and confirmed the file
    } catch (e) {
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Error).catch(() => undefined);
      setPhase("idle");
      setError(e instanceof Error ? e.message : "The upload failed. Please try again.");
    } finally {
      abort.current = null;
    }
  }

  function close() {
    if (phase !== "uploading") return onClose();
    Alert.alert("Stop the upload?", "The file has not been saved yet.", [
      { text: "Keep uploading", style: "cancel" },
      { text: "Stop", style: "destructive", onPress: () => { abort.current?.abort(); onClose(); } },
    ]);
  }

  const sending = phase === "uploading";
  const saving = sending && progress >= 0.999;                                      // all bytes sent, the server is checking and storing

  return (
    <Modal visible animationType="slide" onRequestClose={close} statusBarTranslucent>
      <View style={{ flex: 1, backgroundColor: colors.surfaceSubtle, paddingTop: insets.top }}>
        <View style={{ flexDirection: "row", alignItems: "center", gap: 12, padding: 16, backgroundColor: colors.surface, borderBottomWidth: 1, borderBottomColor: colors.border }}>
          <View style={{ flex: 1 }}>
            <Text style={{ fontSize: 18, fontWeight: "800", color: colors.text }}>{replacing ? `Upload new ${KIND_LABEL[kind].toLowerCase()}` : KIND_UPLOAD[kind]}</Text>
            <Text numberOfLines={1} style={font.small}>{store.name} · {monthLabel(month)}</Text>
          </View>
          <Pressable onPress={close} accessibilityRole="button" accessibilityLabel="Close" hitSlop={12} style={{ width: 44, height: 44, alignItems: "center", justifyContent: "center" }}>
            <Ionicons name="close" size={26} color={colors.text} />
          </Pressable>
        </View>

        <ScrollView contentContainerStyle={{ padding: 16, gap: 16 }} keyboardShouldPersistTaps="handled">
          {phase === "done" ? (
            <View style={{ alignItems: "center", gap: 10, paddingVertical: 36 }} accessibilityLiveRegion="polite">
              <View style={{ width: 72, height: 72, borderRadius: 36, backgroundColor: colors.successSoft, alignItems: "center", justifyContent: "center" }}>
                <Ionicons name="checkmark" size={40} color={colors.success} />
              </View>
              <Text style={{ fontSize: 20, fontWeight: "800", color: colors.text }}>Saved</Text>
              <Text style={[font.small, { textAlign: "center" }]}>
                The {KIND_LABEL[kind].toLowerCase()} for {store.name} is stored.{replacing ? " The earlier file is kept in its history." : ""}
              </Text>
            </View>
          ) : (
            <>
              <View style={{ flexDirection: "row", gap: 10 }}>
                <PickButton icon="camera-outline" label="Take photo" disabled={busy} onPress={() => void add(takePhoto)} />
                <PickButton icon="images-outline" label="Gallery" disabled={busy || hasPdf} onPress={() => void add(() => pickPhotos(Math.max(1, 20 - files.length)))} />
                <PickButton icon="document-text-outline" label="PDF" disabled={busy || files.length > 0} onPress={() => void add(pickPdf)} />
              </View>

              {files.length === 0 ? (
                <View style={{ alignItems: "center", gap: 6, paddingVertical: 28, borderRadius: radius.lg, borderWidth: 1.5, borderStyle: "dashed", borderColor: colors.brand200, backgroundColor: colors.brand50 }}>
                  <Ionicons name="cloud-upload-outline" size={34} color={colors.brand600} />
                  <Text style={{ fontWeight: "700", color: colors.brand700 }}>Take or choose a {kind === "card" ? "photo of the card" : "photo or PDF"}</Text>
                  <Text style={[font.tiny, { textAlign: "center", paddingHorizontal: 24 }]}>Several photos of one document are merged into one PDF. A PDF goes on its own, up to {policy.pdf_max_mb} MB. Photos are shrunk automatically.</Text>
                </View>
              ) : (
                <View style={{ gap: 10 }}>
                  <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 10 }}>
                    {files.map((f, i) => (
                      <View key={`${f.uri}-${i}`} style={{ width: 104 }}>
                        <Pressable
                          onPress={() => setView({ kind: "local", uri: f.uri, name: f.name, type: f.type })}
                          accessibilityRole="button" accessibilityLabel={`Preview ${f.name}`}
                          style={{ width: 104, height: 104, borderRadius: radius.md, overflow: "hidden", borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceMuted, alignItems: "center", justifyContent: "center" }}
                        >
                          {isPdf(f) ? <Ionicons name="document-text-outline" size={40} color={colors.textMuted} /> : <Image source={{ uri: f.uri }} style={{ width: "100%", height: "100%" }} />}
                        </Pressable>
                        <Pressable
                          onPress={() => { if (!busy) setFiles((prev) => prev.filter((_, j) => j !== i)); }}
                          accessibilityRole="button" accessibilityLabel={`Remove ${f.name}`} hitSlop={6} disabled={busy}
                          style={{ position: "absolute", top: 4, right: 4, width: 30, height: 30, borderRadius: 15, backgroundColor: "rgba(0,0,0,0.7)", alignItems: "center", justifyContent: "center" }}
                        >
                          <Ionicons name="close" size={18} color="#fff" />
                        </Pressable>
                        <Text numberOfLines={1} style={[font.tiny, { marginTop: 4 }]}>{f.size ? fmtBytes(f.size) : f.name}</Text>
                      </View>
                    ))}
                  </View>
                  <Text style={font.small}>{describeSelection(files)}. Tap a picture to see it larger.</Text>
                </View>
              )}

              {phase === "preparing" ? <Text style={font.small} accessibilityLiveRegion="polite">Getting the photo ready…</Text> : null}
              {problem ? <Notice tone="warning" text={problem} /> : null}
              {error ? <Notice tone="danger" text={`${error}${files.length ? " Your photo is still here: tap Try again." : ""}`} /> : null}
              {replacing && !error && !problem ? <Text style={font.tiny}>This becomes the current file. The earlier one stays in the history.</Text> : null}
            </>
          )}
        </ScrollView>

        <View style={{ padding: 16, paddingBottom: 16 + insets.bottom, gap: 10, backgroundColor: colors.surface, borderTopWidth: 1, borderTopColor: colors.border }}>
          {sending ? (
            <View style={{ gap: 6 }} accessibilityLiveRegion="polite">
              <ProgressBar value={progress} />
              <Text style={font.small}>{saving ? "Saving…" : `Uploading ${Math.round(progress * 100)}%`}</Text>
            </View>
          ) : null}
          {phase === "done" ? (
            <Button title="Done" onPress={onClose} />
          ) : (
            <Button
              title={error ? "Try again" : files.length > 1 && !hasPdf ? `Upload ${files.length} photos` : "Upload"}
              onPress={() => void send()}
              loading={sending}
              disabled={!canSend && !sending}
            />
          )}
        </View>
      </View>
      <AttachmentViewer source={view} onClose={() => setView(null)} />
    </Modal>
  );
}

function PickButton({ icon, label, onPress, disabled }: { icon: React.ComponentProps<typeof Ionicons>["name"]; label: string; onPress: () => void; disabled?: boolean }) {
  return (
    <Pressable
      onPress={onPress} disabled={disabled} accessibilityRole="button" accessibilityLabel={label} accessibilityState={{ disabled: !!disabled }}
      android_ripple={{ color: colors.brand100 }}
      style={{ flex: 1, minHeight: 72, borderRadius: radius.lg, backgroundColor: colors.surface, borderWidth: 1.5, borderColor: colors.brand200, alignItems: "center", justifyContent: "center", gap: 4, opacity: disabled ? 0.45 : 1 }}
    >
      <Ionicons name={icon} size={26} color={colors.brand600} />
      <Text style={{ fontSize: 13, fontWeight: "700", color: colors.brand700 }}>{label}</Text>
    </Pressable>
  );
}

function Notice({ text, tone }: { text: string; tone: "warning" | "danger" }) {
  const bg = tone === "danger" ? colors.dangerSoft : colors.warningSoft;
  const fg = tone === "danger" ? colors.danger : colors.warning;
  return (
    <View accessibilityRole="alert" style={{ padding: 12, borderRadius: radius.md, backgroundColor: bg }}>
      <Text style={{ color: fg, fontSize: 14, lineHeight: 20 }}>{text}</Text>
    </View>
  );
}
