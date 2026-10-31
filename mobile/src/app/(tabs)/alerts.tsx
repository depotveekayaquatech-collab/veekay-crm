import { Pressable, Text, View } from "react-native";
import { useRouter } from "expo-router";
import { useMarkRead, useNotifications } from "@/api/hooks";
import { Button, Empty, ErrorNote, IconTile, ListSkeleton, Screen } from "@/components/ui";
import { fmtDateTime } from "@/lib/format";
import { colors, font, radius } from "@/theme";

export default function Alerts() {
  const router = useRouter();
  const q = useNotifications();
  const mark = useMarkRead();

  return (
    <Screen onRefresh={() => q.refetch()} refreshing={q.isRefetching && !q.isLoading}>
      <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: 12, marginBottom: 14 }}>
        <Text style={[font.small, { flex: 1 }]}>Updates on your tickets and bills.</Text>
        {(q.data?.unread ?? 0) > 0 && <Button title="Mark all read" variant="ghost" onPress={() => mark.mutate(undefined)} style={{ minHeight: 40, paddingHorizontal: 8 }} />}
      </View>
      {q.isLoading ? <ListSkeleton /> : q.isError ? <ErrorNote message={q.error.message} onRetry={() => q.refetch()} /> : q.data!.items.length === 0 ? (
        <Empty title="No alerts yet" text="You will see replies and status changes on your tickets here." />
      ) : (
        <View style={{ gap: 10 }}>
          {q.data!.items.map((n) => (
            <Pressable
              key={n.id}
              onPress={() => {
                if (!n.read) mark.mutate([n.id]);
                if (n.kind === "ticket" && n.ref_id) router.push(`/tickets/${n.ref_id}`);
                else if (n.kind === "bill") router.push({ pathname: "/documents", params: { kind: "bill" } });
              }}
              accessibilityRole="button"
              accessibilityLabel={`${n.read ? "" : "Unread. "}${n.title}`}
              android_ripple={{ color: colors.brand100 }}
              style={({ pressed }) => ({ padding: 14, borderRadius: radius.lg, borderWidth: 1, borderColor: n.read ? colors.border : colors.brand200, backgroundColor: n.read ? colors.surface : colors.brand50, flexDirection: "row", gap: 12, opacity: pressed ? 0.9 : 1 })}
            >
              <IconTile icon={n.kind === "bill" ? "receipt-outline" : n.kind === "ticket" ? "ticket-outline" : "notifications-outline"}
                bg={n.read ? colors.surfaceMuted : colors.brand100} fg={n.read ? colors.textMuted : colors.brand700} size={38} />
              <View style={{ flex: 1 }}>
                <View style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
                  <Text style={{ flex: 1, fontSize: 15, fontWeight: n.read ? "600" : "800", color: colors.text }}>{n.title}</Text>
                  {!n.read ? <View style={{ width: 9, height: 9, borderRadius: 5, backgroundColor: colors.brand500 }} /> : null}
                </View>
                <Text numberOfLines={2} style={{ marginTop: 3, color: colors.textMuted, lineHeight: 20 }}>{n.body}</Text>
                <Text style={[font.tiny, { marginTop: 6 }]}>{fmtDateTime(n.created_at)}</Text>
              </View>
            </Pressable>
          ))}
        </View>
      )}
    </Screen>
  );
}
