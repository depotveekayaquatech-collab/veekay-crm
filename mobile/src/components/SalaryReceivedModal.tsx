import { Modal, Pressable, Text, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import { useQueryClient } from "@tanstack/react-query";
import { staffApi } from "@/api/staff";
import { useUnseenPayslips } from "@/api/staffHooks";
import { fmtMoney } from "@/lib/format";
import { colors, font, radius, shadow } from "@/theme";

/** Shown once, the next time the employee opens the app after an admin has paid their salary. */
export function SalaryReceivedModal() {
  const router = useRouter();
  const qc = useQueryClient();
  const q = useUnseenPayslips();
  const slip = q.data?.items[0];
  if (!slip) return null;

  async function close(openPayslips: boolean) {
    // mark it seen first, so it does not come back; a failure just means it shows once more
    await staffApi.payslipSeen(slip!.id).catch(() => undefined);
    await qc.invalidateQueries({ queryKey: ["s-payslips-unseen"] });
    void qc.invalidateQueries({ queryKey: ["s-payslips"] });
    if (openPayslips) router.push("/staff/payslips");
  }

  return (
    <Modal visible transparent animationType="fade" onRequestClose={() => void close(false)}>
      <View style={{ flex: 1, backgroundColor: "rgba(0,0,0,0.5)", alignItems: "center", justifyContent: "center", padding: 24 }}>
        <View accessibilityViewIsModal style={{ width: "100%", maxWidth: 380, backgroundColor: colors.surface, borderRadius: radius.lg, padding: 24, alignItems: "center", gap: 8, ...shadow.card }}>
          <View style={{ width: 64, height: 64, borderRadius: 32, backgroundColor: colors.successSoft, alignItems: "center", justifyContent: "center" }}>
            <Ionicons name="checkmark" size={36} color={colors.success} />
          </View>
          <Text style={{ fontSize: 20, fontWeight: "800", color: colors.text, marginTop: 4 }}>Salary received</Text>
          <Text style={[font.small, { textAlign: "center" }]}>Your salary for {slip.month_label} has been paid.</Text>
          <Text style={{ fontSize: 34, fontWeight: "800", color: colors.text, marginVertical: 4 }}>{fmtMoney(slip.amount)}</Text>
          <Text style={font.tiny}>{slip.paid_days} of {slip.days_in_month} days paid</Text>
          <View style={{ flexDirection: "row", gap: 10, marginTop: 14, width: "100%" }}>
            <Pressable onPress={() => void close(false)} accessibilityRole="button" style={{ flex: 1, height: 50, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, alignItems: "center", justifyContent: "center" }}>
              <Text style={{ fontWeight: "800", color: colors.text }}>Got it</Text>
            </Pressable>
            <Pressable onPress={() => void close(true)} accessibilityRole="button" style={{ flex: 1, height: 50, borderRadius: radius.md, backgroundColor: colors.brand600, alignItems: "center", justifyContent: "center" }}>
              <Text style={{ fontWeight: "800", color: colors.white }}>View payslip</Text>
            </Pressable>
          </View>
        </View>
      </View>
    </Modal>
  );
}
