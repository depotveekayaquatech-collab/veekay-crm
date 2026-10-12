import { useRef, useState } from "react";
import { Pressable, Text, TextInput, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { staffApi } from "@/api/staff";
import { useAuth } from "@/auth/AuthProvider";
import { Button, ErrorNote, Field, Screen } from "@/components/ui";
import { colors } from "@/theme";

/** Shown to an employee whose password was set by an admin: nothing else works until they choose their own. */
export default function ChangePassword() {
  const { reloadStaff, signOut } = useAuth();
  const insets = useSafeAreaInsets();
  const nextRef = useRef<TextInput>(null);
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [show, setShow] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const rules = [
    { ok: next.length >= 8, text: "At least 8 characters" },
    { ok: /[A-Za-z]/.test(next) && /\d/.test(next), text: "A letter and a number" },
    { ok: next !== current && next.length > 0, text: "Different from the temporary password" },
  ];

  async function submit() {
    setError(null);
    setBusy(true);
    try {
      await staffApi.changePassword(current, next);
      await reloadStaff();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't change the password.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Screen keyboard style={{ paddingTop: insets.top + 24 }}>
      <View style={{ width: 64, height: 64, borderRadius: 32, backgroundColor: colors.brand50, alignItems: "center", justifyContent: "center", marginBottom: 16 }}>
        <Ionicons name="key-outline" size={30} color={colors.brand600} />
      </View>
      <Text style={{ fontSize: 24, fontWeight: "800", color: colors.text }}>Choose your own password</Text>
      <Text style={{ marginTop: 6, color: colors.textMuted, lineHeight: 21 }}>Your password was set by an admin. Pick a new one that only you know to continue.</Text>

      <View style={{ gap: 16, marginTop: 22 }}>
        <Field label="Temporary password" value={current} onChangeText={setCurrent} secureTextEntry autoCapitalize="none" autoComplete="current-password" returnKeyType="next" onSubmitEditing={() => nextRef.current?.focus()} />
        <Field
          ref={nextRef}
          label="New password"
          value={next}
          onChangeText={setNext}
          secureTextEntry={!show}
          autoCapitalize="none"
          autoComplete="new-password"
          right={<Pressable onPress={() => setShow((v) => !v)} hitSlop={10} accessibilityRole="button" accessibilityLabel={show ? "Hide password" : "Show password"}><Ionicons name={show ? "eye-off-outline" : "eye-outline"} size={22} color={colors.textMuted} /></Pressable>}
        />
        <View style={{ gap: 6 }}>
          {rules.map((r) => (
            <View key={r.text} style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
              <Ionicons name={r.ok ? "checkmark-circle" : "ellipse-outline"} size={18} color={r.ok ? colors.success : colors.textFaint} />
              <Text style={{ color: r.ok ? colors.text : colors.textMuted, fontSize: 13 }}>{r.text}</Text>
            </View>
          ))}
        </View>
        {error ? <ErrorNote message={error} /> : null}
        <Button title="Save and continue" onPress={submit} loading={busy} disabled={!current || rules.some((r) => !r.ok)} />
        <Button title="Sign out" variant="ghost" onPress={() => void signOut()} />
      </View>
    </Screen>
  );
}
