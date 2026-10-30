import { useCallback, useEffect, useRef, useState } from "react";
import { Linking, Pressable, Text, TextInput, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { CameraView, useCameraPermissions } from "expo-camera";

import { useIsFocused, useRouter } from "expo-router";
import * as Haptics from "expo-haptics";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import type { Direction } from "@/api/staff";
import { useScanStores } from "@/api/staffHooks";
import { Button } from "@/components/ui";
import { StorePicker } from "@/components/StorePicker";
import { flushQueue, startAutoFlush, submitScan } from "@/lib/scanQueue";
import { useScanQueue } from "@/lib/useScanQueue";
import { colors, radius } from "@/theme";

interface Shown { tone: "ok" | "warn" | "bad" | "wait"; title: string; sub: string }

/** Scanner in the style of payment apps: full-screen camera, a frame to aim at, the result in a card at the bottom. */
export default function Scan() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const focused = useIsFocused();
  const [perm, askPerm] = useCameraPermissions();
  const stores = useScanStores();
  const queue = useScanQueue();
  const [direction, setDirection] = useState<Direction>("IN");
  const [store, setStore] = useState("");
  const [torch, setTorch] = useState(false);
  const [manual, setManual] = useState(false);
  const [text, setText] = useState("");
  const [shown, setShown] = useState<Shown | null>(null);
  const [count, setCount] = useState(0);
  const last = useRef({ serial: "", at: 0 });
  const busy = useRef(false);

  useEffect(() => startAutoFlush(), []);

  const storeName = stores.data?.find((s) => s.id === store)?.name;
  const needStore = direction === "IN" && !store;

  const handle = useCallback(async (raw: string) => {
    const serial = raw.trim();
    const now = Date.now();
    if (!serial || busy.current) return;
    if (serial === last.current.serial && now - last.current.at < 3000) return;    // the same code still in view
    last.current = { serial, at: now };
    busy.current = true;
    try {
      const out = await submitScan(serial, direction, direction === "IN" ? store : store || null);
      if (out.kind === "done") {
        setCount((c) => c + 1);
        Haptics.notificationAsync(out.result.warning ? Haptics.NotificationFeedbackType.Warning : Haptics.NotificationFeedbackType.Success).catch(() => undefined);
        setShown({
          tone: out.result.warning ? "warn" : "ok",
          title: out.result.duplicate ? "Already recorded" : direction === "IN" ? "Scanned IN" : "Scanned OUT",
          sub: `${out.result.bottle.serial}${out.result.scan.store_name ? ` · ${out.result.scan.store_name}` : ""}${out.result.warning ? `\n${out.result.warning}` : ""}`,
        });
      } else if (out.kind === "queued") {
        setCount((c) => c + 1);
        Haptics.notificationAsync(Haptics.NotificationFeedbackType.Warning).catch(() => undefined);
        setShown({ tone: "wait", title: "Saved on this phone", sub: `${serial}\nNo connection. It will be sent automatically.` });
      } else {
        Haptics.notificationAsync(Haptics.NotificationFeedbackType.Error).catch(() => undefined);
        setShown({ tone: "bad", title: "Not accepted", sub: `${serial}\n${out.reason}` });
      }
    } finally {
      busy.current = false;
    }
  }, [direction, store]);

  if (!perm) return <View style={{ flex: 1, backgroundColor: colors.ink950 }} />;

  if (!perm.granted) {
    return (
      <View style={{ flex: 1, backgroundColor: colors.surface, alignItems: "center", justifyContent: "center", padding: 32, gap: 14 }}>
        <View style={{ width: 84, height: 84, borderRadius: 42, backgroundColor: colors.brand50, alignItems: "center", justifyContent: "center" }}>
          <Ionicons name="qr-code-outline" size={40} color={colors.brand600} />
        </View>
        <Text style={{ fontSize: 20, fontWeight: "800", color: colors.text, textAlign: "center" }}>Camera access needed</Text>
        <Text style={{ color: colors.textMuted, textAlign: "center", lineHeight: 21 }}>Veekay uses the camera only to read the QR code on a bottle. Nothing is recorded or uploaded from the camera.</Text>
        <Button title={perm.canAskAgain ? "Allow camera" : "Open settings"} onPress={() => (perm.canAskAgain ? askPerm() : Linking.openSettings())} style={{ alignSelf: "stretch" }} />
      </View>
    );
  }

  const toneColor = { ok: colors.success, warn: colors.warning, bad: colors.danger, wait: colors.brand600 }[shown?.tone ?? "ok"];

  return (
    <View style={{ flex: 1, backgroundColor: "#000" }}>
      {focused && (
        <CameraView
          style={{ flex: 1 }}
          facing="back"
          enableTorch={torch}
          barcodeScannerSettings={{ barcodeTypes: ["qr"] }}
          onBarcodeScanned={needStore || manual ? undefined : (r) => void handle(r.data)}
        />
      )}

      {/* Dimmed surround with a clear viewfinder */}
      <View pointerEvents="none" style={{ position: "absolute", inset: 0, alignItems: "center", justifyContent: "center" }}>
        <View style={{ width: 250, height: 250, borderRadius: 28, borderWidth: 3, borderColor: needStore ? colors.warning : "rgba(255,255,255,0.95)", backgroundColor: "transparent" }} />
        <Text style={{ marginTop: 18, color: "#fff", fontWeight: "700", fontSize: 14, textShadowColor: "rgba(0,0,0,0.6)", textShadowRadius: 6 }}>
          {needStore ? "Choose the store first" : "Point the camera at the bottle's QR code"}
        </Text>
      </View>

      {/* Top controls */}
      <View style={{ position: "absolute", top: 12, left: 12, right: 12, gap: 10 }}>
        <View style={{ flexDirection: "row", backgroundColor: "rgba(0,0,0,0.55)", borderRadius: radius.pill, padding: 4 }}>
          {(["IN", "OUT"] as const).map((d) => (
            <Pressable key={d} onPress={() => setDirection(d)} accessibilityRole="button" accessibilityState={{ selected: direction === d }}
              style={{ flex: 1, height: 44, borderRadius: radius.pill, alignItems: "center", justifyContent: "center", backgroundColor: direction === d ? (d === "IN" ? colors.success : colors.brand600) : "transparent" }}>
              <Text style={{ color: "#fff", fontWeight: "800", fontSize: 15 }}>{d === "IN" ? "Scan IN (to a store)" : "Scan OUT (back)"}</Text>
            </Pressable>
          ))}
        </View>
        <View style={{ backgroundColor: colors.surface, borderRadius: radius.lg, padding: 10 }}>
          <StorePicker value={store} onChange={setStore} stores={stores.data ?? []} label={direction === "IN" ? "Store (required)" : "Store (optional)"} allLabel={direction === "OUT" ? "The store it is at" : undefined} />
        </View>
      </View>

      {/* Right-hand tools */}
      <View style={{ position: "absolute", right: 14, top: 230, gap: 12 }}>
        <Tool icon={torch ? "flash" : "flash-outline"} label="Torch" on={torch} onPress={() => setTorch((t) => !t)} />
        <Tool icon="keypad-outline" label="Type code" on={manual} onPress={() => setManual((m) => !m)} />
      </View>

      {/* Bottom: result card + counters */}
      <View style={{ position: "absolute", left: 0, right: 0, bottom: 0, padding: 12, paddingBottom: insets.bottom + 12, gap: 10 }}>
        {manual && (
          <View style={{ flexDirection: "row", gap: 8, backgroundColor: colors.surface, borderRadius: radius.lg, padding: 10 }}>
            <TextInput value={text} onChangeText={(t) => setText(t.toUpperCase())} autoCapitalize="characters" autoCorrect={false} placeholder="VK-XXXX-XXXX" placeholderTextColor={colors.textFaint}
              accessibilityLabel="Bottle code" onSubmitEditing={() => { void handle(text); setText(""); }} returnKeyType="done"
              style={{ flex: 1, height: 46, fontSize: 16, fontWeight: "700", color: colors.text, paddingHorizontal: 10, backgroundColor: colors.surfaceSubtle, borderRadius: radius.md }} />
            <Button title="Add" disabled={needStore || !text.trim()} onPress={() => { void handle(text); setText(""); }} style={{ minHeight: 46 }} />
          </View>
        )}
        {shown && (
          <Pressable onPress={() => setShown(null)} accessibilityRole="alert" style={{ backgroundColor: colors.surface, borderRadius: radius.lg, padding: 14, flexDirection: "row", gap: 12, borderLeftWidth: 6, borderLeftColor: toneColor }}>
            <Ionicons name={shown.tone === "ok" ? "checkmark-circle" : shown.tone === "bad" ? "close-circle" : shown.tone === "wait" ? "cloud-offline" : "alert-circle"} size={28} color={toneColor} />
            <View style={{ flex: 1 }}>
              <Text style={{ fontSize: 16, fontWeight: "800", color: colors.text }}>{shown.title}</Text>
              <Text style={{ color: colors.textMuted, marginTop: 2, lineHeight: 19 }}>{shown.sub}</Text>
            </View>
          </Pressable>
        )}
        <View style={{ flexDirection: "row", gap: 10 }}>
          <View style={{ flex: 1, backgroundColor: "rgba(0,0,0,0.6)", borderRadius: radius.pill, paddingHorizontal: 16, height: 44, justifyContent: "center" }}>
            <Text style={{ color: "#fff", fontWeight: "700" }}>{count} scanned{storeName ? ` · ${storeName}` : ""}</Text>
          </View>
          <Pressable onPress={() => (queue.pending.length ? void flushQueue().then(() => router.push("/staff/sync")) : router.push("/staff/sync"))} accessibilityRole="button"
            style={{ height: 44, borderRadius: radius.pill, paddingHorizontal: 16, flexDirection: "row", alignItems: "center", gap: 6, backgroundColor: queue.pending.length ? colors.warning : "rgba(0,0,0,0.6)" }}>
            <Ionicons name={queue.pending.length ? "cloud-upload-outline" : "checkmark-done"} size={18} color="#fff" />
            <Text style={{ color: "#fff", fontWeight: "700" }}>{queue.pending.length ? `${queue.pending.length} waiting` : "Synced"}</Text>
          </Pressable>
        </View>
      </View>
    </View>
  );
}

function Tool({ icon, label, on, onPress }: { icon: React.ComponentProps<typeof Ionicons>["name"]; label: string; on: boolean; onPress: () => void }) {
  return (
    <Pressable onPress={onPress} accessibilityRole="button" accessibilityLabel={label} accessibilityState={{ selected: on }}
      style={{ width: 48, height: 48, borderRadius: 24, alignItems: "center", justifyContent: "center", backgroundColor: on ? colors.brand600 : "rgba(0,0,0,0.55)" }}>
      <Ionicons name={icon} size={22} color="#fff" />
    </Pressable>
  );
}

