import { Alert, Image, Pressable, Text, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { colors, radius } from "@/theme";
import { pickPdf, pickPhotos, takePhoto, type Picked } from "@/lib/files";

/** Add photos with the camera or the gallery (and optionally a PDF). Shows thumbnails with a remove button. */
export function PhotoField({
  files, onChange, max = 5, label = "Photos", allowPdf = false,
}: { files: Picked[]; onChange: (f: Picked[]) => void; max?: number; label?: string; allowPdf?: boolean }) {
  const room = max - files.length;

  function add() {
    const buttons = [
      { text: "Take a photo", onPress: async () => onChange([...files, ...(await takePhoto())].slice(0, max)) },
      { text: "Choose from gallery", onPress: async () => onChange([...files, ...(await pickPhotos(room))].slice(0, max)) },
      ...(allowPdf ? [{ text: "Choose a PDF", onPress: async () => onChange([...files, ...(await pickPdf())].slice(0, max)) }] : []),
      { text: "Cancel", style: "cancel" as const },
    ];
    Alert.alert("Add", undefined, buttons);
  }

  return (
    <View style={{ gap: 8 }}>
      <Text style={{ fontSize: 13, fontWeight: "600", color: colors.text }}>
        {label} <Text style={{ fontWeight: "400", color: colors.textMuted }}>(up to {max})</Text>
      </Text>
      <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 10 }}>
        {files.map((f, i) => (
          <View key={`${f.uri}-${i}`} style={{ width: 84, height: 84, borderRadius: radius.md, overflow: "hidden", borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceMuted }}>
            {f.type.startsWith("image/") ? (
              <Image source={{ uri: f.uri }} style={{ width: "100%", height: "100%" }} accessibilityLabel={`Photo ${i + 1}`} />
            ) : (
              <View style={{ flex: 1, alignItems: "center", justifyContent: "center", padding: 4 }}>
                <Ionicons name="document-text-outline" size={26} color={colors.textMuted} />
                <Text numberOfLines={1} style={{ fontSize: 10, color: colors.textMuted }}>{f.name}</Text>
              </View>
            )}
            <Pressable
              onPress={() => onChange(files.filter((_, j) => j !== i))}
              accessibilityRole="button"
              accessibilityLabel={`Remove ${f.name}`}
              hitSlop={6}
              style={{ position: "absolute", top: 4, right: 4, width: 24, height: 24, borderRadius: 12, backgroundColor: "rgba(0,0,0,0.65)", alignItems: "center", justifyContent: "center" }}
            >
              <Ionicons name="close" size={15} color="#fff" />
            </Pressable>
          </View>
        ))}
        {room > 0 && (
          <Pressable
            onPress={add}
            accessibilityRole="button"
            accessibilityLabel="Add photo"
            style={{ width: 84, height: 84, borderRadius: radius.md, borderWidth: 1.5, borderStyle: "dashed", borderColor: colors.brand200, backgroundColor: colors.brand50, alignItems: "center", justifyContent: "center", gap: 2 }}
          >
            <Ionicons name="camera-outline" size={24} color={colors.brand600} />
            <Text style={{ fontSize: 12, fontWeight: "600", color: colors.brand600 }}>Add</Text>
          </Pressable>
        )}
      </View>
    </View>
  );
}
