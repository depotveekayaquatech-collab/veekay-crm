import { Pressable, Text, View } from "react-native";
import { useRouter } from "expo-router";
import { useMarkStaffAlertsRead, useStaffAlerts } from "@/api/staffHooks";
import { useAuth } from "@/auth/AuthProvider";
import { Button, Empty, ErrorNote, ListSkeleton, Screen } from "@/components/ui";
import { fmtDateTime } from "@/lib/format";
import { colors, font, radius } from "@/theme";

/** Alerts for an employee or admin: leave requests and decisions, tickets assigned or raised by a POC. */
export default function StaffAlerts() {
  const router = useRouter();
  const { hasPermission } = useAuth();
  const q = useStaffAlerts();
  const mark = useMarkStaffAlertsRead();

  function open(kind: string, title: string) {
    if (kind !== "leave") return;                                   // tickets are handled on the web app
    // a new request goes to the approvals list for reviewers; a decision goes to the person's own leave page
    router.push(hasPermission("leave.review") && title === "New leave request" ? "/staff/admin/leaves" : "/staff/leave");
  }

  return (
    <Screen onRefresh={() => q.refetch()} refreshing={q.isRefetching && !q.isLoading}>
      <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: 12, marginBottom: 14 }}>
        <Text style={[font.small, { flex: 1 }]}>Leave requests and decisions, and tickets for you.</Text>
        {(q.data?.unread ?? 0) > 0 && <Button title="Mark all read" variant="ghost" onPress={() => mark.mutate(undefined)} style={{ minHeight: 40, paddingHorizontal: 8 }} />}
      </View>
      {q.isLoading ? <ListSkeleton /> : q.isError ? <ErrorNote message={q.error.message} onRetry={() => q.refetch()} /> : q.data!.items.length === 0 ? (
        <Empty title="No alerts yet" text="You will see leave decisions and new tickets here." />
      ) : (
        <View style={{ gap: 10 }}>
          {q.data!.items.map((n) => (
            <Pressable
              key={n.id}
              onPress={() => { if (!n.read) mark.mutate([n.id]); open(n.kind, n.title); }}
              accessibilityRole="button"
              accessibilityLabel={`${n.read ? "" : "Unread. "}${n.title}`}
              android_ripple={{ color: colors.brand100 }}
              style={{ padding: 14, borderRadius: radius.lg, borderWidth: 1, borderColor: n.read ? colors.border : colors.brand200, backgroundColor: n.read ? colors.surface : colors.brand50 }}
            >
              <Text style={{ fontSize: 15, fontWeight: "700", color: colors.text }}>{n.title}</Text>
              <Text numberOfLines={2} style={{ marginTop: 3, color: colors.textMuted, lineHeight: 20 }}>{n.body}</Text>
              <Text style={[font.tiny, { marginTop: 6 }]}>{fmtDateTime(n.created_at)}</Text>
            </Pressable>
          ))}
        </View>
      )}
    </Screen>
  );
}
