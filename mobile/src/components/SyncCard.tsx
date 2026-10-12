import { Alert, Text, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useSyncNow, useSyncStatus } from "@/api/adminHooks";
import { Button, Card } from "@/components/ui";
import { markRefreshed } from "@/lib/dailyRefresh";
import { colors, font } from "@/theme";

/** "Today 10:00 am" / "Yesterday 10:00 am" / "12 Oct, 10:00 am" */
function when(iso: string): string {
  const d = new Date(iso);
  const t = d.toLocaleTimeString("en-IN", { hour: "numeric", minute: "2-digit" });
  const days = Math.round((new Date(new Date().toDateString()).getTime() - new Date(d.toDateString()).getTime()) / 86_400_000);
  if (days === 0) return `Today ${t}`;
  if (days === 1) return `Yesterday ${t}`;
  if (days === -1) return `Tomorrow ${t}`;
  return `${d.toLocaleDateString("en-IN", { day: "numeric", month: "short" })}, ${t}`;
}

/** Shows when the CRM last pulled the sheets and when it will next, with "Sync now" for people allowed to run it. */
export function SyncCard() {
  const qc = useQueryClient();
  const status = useSyncStatus();
  const sync = useSyncNow();
  const [refreshing, setRefreshing] = useState(false);
  const s = status.data;

  function runSync() {
    sync.mutate(undefined, {
      onSuccess: async (r) => {
        await markRefreshed();
        const all = [...r.stores, ...r.orders];
        Alert.alert("Synced", all.length ? all.map((x) => `${x.platform}: +${x.created} new, ${x.updated} updated`).join("\n") : "Nothing to pull. No sheets are set up.");
      },
      onError: (e) => Alert.alert("Couldn't sync", e.message),
    });
  }

  async function refresh() {
    setRefreshing(true);
    await qc.invalidateQueries();
    await markRefreshed();
    setRefreshing(false);
  }

  return (
    <Card>
      <View style={{ flexDirection: "row", alignItems: "center", gap: 12 }}>
        <View style={{ width: 40, height: 40, borderRadius: 12, backgroundColor: colors.brand50, alignItems: "center", justifyContent: "center" }}>
          <Ionicons name="sync-outline" size={21} color={colors.brand600} />
        </View>
        <View style={{ flex: 1 }}>
          <Text style={{ fontSize: 15, fontWeight: "700", color: colors.text }}>Data from the CRM</Text>
          <Text style={font.small}>
            {s?.last_run_at ? `Synced ${when(s.last_run_at)}${s.last_run_source === "manual" ? ` by ${s.last_run_by ?? "someone"}` : " (daily)"}` : status.isLoading ? "Checking…" : "Not synced yet"}
          </Text>
          {s?.next_run_at ? <Text style={font.tiny}>Next daily sync {when(s.next_run_at)}</Text> : null}
        </View>
      </View>
      {s?.last_run_warnings ? <Text style={{ color: colors.warning, fontSize: 12, marginTop: 8 }}>{s.last_run_warnings} warning{s.last_run_warnings === 1 ? "" : "s"} in the last sync. Check the web Data sync page.</Text> : null}
      <View style={{ marginTop: 12 }}>
        {s?.can_sync ? (
          <Button title={sync.isPending ? "Syncing from sheets…" : "Sync now"} onPress={runSync} loading={sync.isPending} />
        ) : (
          <Button title="Refresh data" variant="secondary" onPress={refresh} loading={refreshing} />
        )}
      </View>
    </Card>
  );
}
