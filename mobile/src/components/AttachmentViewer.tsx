import { useState } from "react";
import { ActivityIndicator, Image, Linking, Modal, Pressable, Text, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useDocFile } from "@/api/complianceHooks";
import { Button } from "@/components/ui";
import { openWithPhone } from "@/lib/files";
import { isPdf } from "@/lib/compliance";
import { colors, radius } from "@/theme";

/** What to show: a file chosen on this phone (before uploading) or a stored document (optionally an earlier version). */
export type ViewerSource =
  | { kind: "local"; uri: string; name: string; type: string }
  | { kind: "stored"; id: string; version?: number; title: string };

/**
 * A photo at full size, or a PDF handed to the phone's own viewer. A stored file is fetched only now, with a short-lived link
 * (or an authenticated copy), so nothing downloads until someone asks to see it.
 */
export function AttachmentViewer({ source, onClose }: { source: ViewerSource | null; onClose: () => void }) {
  const insets = useSafeAreaInsets();
  return (
    <Modal visible={!!source} animationType="fade" onRequestClose={onClose} statusBarTranslucent transparent={false}>
      <View style={{ flex: 1, backgroundColor: colors.ink950, paddingTop: insets.top }}>
        <View style={{ flexDirection: "row", alignItems: "center", gap: 12, paddingHorizontal: 16, height: 56 }}>
          <Text numberOfLines={1} style={{ flex: 1, color: colors.white, fontSize: 16, fontWeight: "700" }}>
            {source ? (source.kind === "local" ? source.name : source.title) : ""}
          </Text>
          <Pressable onPress={onClose} accessibilityRole="button" accessibilityLabel="Close" hitSlop={12} style={{ width: 44, height: 44, alignItems: "center", justifyContent: "center" }}>
            <Ionicons name="close" size={28} color={colors.white} />
          </Pressable>
        </View>
        {source ? (source.kind === "local" ? <LocalBody source={source} /> : <StoredBody source={source} />) : null}
        <View style={{ height: insets.bottom + 8 }} />
      </View>
    </Modal>
  );
}

function PdfPanel({ name, onOpen }: { name: string; onOpen: () => void }) {
  return (
    <View style={{ flex: 1, alignItems: "center", justifyContent: "center", padding: 32, gap: 16 }}>
      <Ionicons name="document-text-outline" size={72} color={colors.aqua200} />
      <Text style={{ color: colors.white, fontSize: 16, fontWeight: "700", textAlign: "center" }}>{name}</Text>
      <Text style={{ color: "rgba(255,255,255,0.7)", textAlign: "center" }}>A PDF opens in your phone's own viewer.</Text>
      <Button title="Open PDF" onPress={onOpen} icon={<Ionicons name="open-outline" size={20} color={colors.white} />} style={{ alignSelf: "stretch" }} />
    </View>
  );
}

function PhotoPanel({ uri, onOpen, onBroken }: { uri: string; onOpen: () => void; onBroken: () => void }) {
  return (
    <View style={{ flex: 1 }}>
      <Image source={{ uri }} resizeMode="contain" onError={onBroken} accessibilityLabel="Photo" style={{ flex: 1, margin: 8, borderRadius: radius.md }} />
      <View style={{ paddingHorizontal: 16, paddingTop: 8 }}>
        <Button title="Open in another app to zoom" variant="secondary" onPress={onOpen} icon={<Ionicons name="expand-outline" size={20} color={colors.brand700} />} />
      </View>
    </View>
  );
}

function LocalBody({ source }: { source: Extract<ViewerSource, { kind: "local" }> }) {
  const [broken, setBroken] = useState(false);
  if (isPdf(source)) return <PdfPanel name={source.name} onOpen={() => void openWithPhone(source.uri, source.type)} />;
  if (broken) return <Message text="This photo can't be shown." />;
  return <PhotoPanel uri={source.uri} onOpen={() => void openWithPhone(source.uri, source.type)} onBroken={() => setBroken(true)} />;
}

function StoredBody({ source }: { source: Extract<ViewerSource, { kind: "stored" }> }) {
  const file = useDocFile(source.id, source.version, true);
  const [broken, setBroken] = useState(false);
  if (file.error) return <Message text={file.error.message || "Couldn't open this file."} onRetry={file.retry} />;
  if (file.loading || !file.uri || !file.contentType) {
    return <View style={{ flex: 1, alignItems: "center", justifyContent: "center" }}><ActivityIndicator size="large" color={colors.white} /></View>;
  }
  const open = () => {
    // A direct link opens in the browser or PDF viewer; a temporary local copy goes to the phone's "Open with".
    if (file.uri!.startsWith("http")) void Linking.openURL(file.uri!);
    else void openWithPhone(file.uri!, file.contentType!);
  };
  if (file.contentType === "application/pdf") return <PdfPanel name={file.fileName ?? source.title} onOpen={open} />;
  if (broken) return <Message text="This photo can't be shown right now. Try again." onRetry={() => { setBroken(false); file.retry(); }} />;
  return <PhotoPanel uri={file.uri} onOpen={open} onBroken={() => setBroken(true)} />;
}

function Message({ text, onRetry }: { text: string; onRetry?: () => void }) {
  return (
    <View style={{ flex: 1, alignItems: "center", justifyContent: "center", padding: 32, gap: 16 }}>
      <Ionicons name="alert-circle-outline" size={56} color={colors.aqua200} />
      <Text style={{ color: colors.white, fontSize: 16, textAlign: "center" }}>{text}</Text>
      {onRetry ? <Button title="Try again" onPress={onRetry} /> : null}
    </View>
  );
}
