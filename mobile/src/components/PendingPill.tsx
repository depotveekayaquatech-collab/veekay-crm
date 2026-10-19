import { Text, View } from "react-native";
import { pendingLabel, pendingTone, radius } from "@/theme";

/** How long a store has been waiting for its entry: a pill that gets warmer the longer it is. It never grows wider than its row. */
export function PendingPill({ days }: { days: number }) {
  const t = pendingTone(days);
  return (
    <View
      accessible
      accessibilityLabel={pendingLabel(days)}
      style={{ alignSelf: "flex-start", flexShrink: 0, flexDirection: "row", alignItems: "center", gap: 6, paddingHorizontal: 10, paddingVertical: 4, borderRadius: radius.pill, backgroundColor: t.bg }}
    >
      <View style={{ width: 6, height: 6, borderRadius: 3, backgroundColor: t.dot }} />
      <Text style={{ fontSize: 12, fontWeight: "800", color: t.fg }}>{pendingLabel(days)}</Text>
    </View>
  );
}
