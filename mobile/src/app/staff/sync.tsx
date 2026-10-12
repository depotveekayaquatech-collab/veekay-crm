import { useState } from "react";
import { Alert, Text, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { Button, Card, Empty, Screen, SectionTitle } from "@/components/ui";
import { clearRejected, flushQueue } from "@/lib/scanQueue";
import { useScanQueue } from "@/lib/useScanQueue";
import { fmtDateTime } from "@/lib/format";
import { colors, font } from "@/theme";

export default function Sync() {
  const q = useScanQueue();
  const [busy, setBusy] = useState(false);

  async function sync() {
    setBusy(true);
    const r = await flushQueue();
    setBusy(false);
    Alert.alert(r.left ? "Not everything was sent" : "All synced", r.left ? `${r.left} scan${r.left === 1 ? "" : "s"} still waiting. Check your connection and try again.` : `${r.sent} scan${r.sent === 1 ? "" : "s"} sent.`);
  }

  return (
    <Screen>
      <Text style={font.small}>Bottle scans are saved on this phone the moment you scan, and sent when there is a connection. Sending a scan twice never counts a bottle twice.</Text>
      <Button title={busy ? "Sending…" : "Send now"} onPress={sync} loading={busy} disabled={q.pending.length === 0} icon={<Ionicons name="cloud-upload-outline" size={20} color="#fff" />} style={{ marginTop: 14 }} />

      <SectionTitle>Waiting to send ({q.pending.length})</SectionTitle>
      {q.pending.length === 0 ? <Empty title="Nothing waiting" text="Every scan has been sent." /> : (
        <Card style={{ padding: 0, overflow: "hidden" }}>
          {q.pending.map((p, i) => (
            <View key={p.scan_id} style={{ padding: 14, borderTopWidth: i ? 1 : 0, borderTopColor: colors.border, flexDirection: "row", justifyContent: "space-between", gap: 10 }}>
              <View>
                <Text style={{ fontWeight: "700", color: colors.text }}>{p.serial}</Text>
                <Text style={font.tiny}>{fmtDateTime(p.scanned_at)}</Text>
              </View>
              <Text style={{ fontWeight: "700", color: p.direction === "IN" ? colors.success : colors.brand600 }}>{p.direction}</Text>
            </View>
          ))}
        </Card>
      )}

      {q.rejected.length > 0 && (
        <>
          <SectionTitle action={<Text onPress={() => void clearRejected()} accessibilityRole="button" style={{ color: colors.brand600, fontWeight: "700" }}>Clear</Text>}>Not accepted ({q.rejected.length})</SectionTitle>
          <Card style={{ padding: 0, overflow: "hidden" }}>
            {q.rejected.map((p, i) => (
              <View key={p.scan_id} style={{ padding: 14, borderTopWidth: i ? 1 : 0, borderTopColor: colors.border }}>
                <Text style={{ fontWeight: "700", color: colors.text }}>{p.serial} · {p.direction}</Text>
                <Text style={{ color: colors.danger, marginTop: 2 }}>{p.reason}</Text>
              </View>
            ))}
          </Card>
        </>
      )}
    </Screen>
  );
}
