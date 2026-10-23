import { useState } from "react";
import { Text, View } from "react-native";
import { useRouter } from "expo-router";
import { ApiError, request } from "@/api/client";
import { Button, Field, Screen, Title } from "@/components/ui";
import { colors } from "@/theme";

const MIN = 10; // keep in step with PASSWORD_MIN_LENGTH on the server

/** Forgot password: Employee ID -> a 6-digit code emailed to the address on the account -> a new password. */
export default function ForgotPasswordScreen() {
  const router = useRouter();
  const [step, setStep] = useState<"id" | "code">("id");
  const [employeeId, setEmployeeId] = useState("");
  const [code, setCode] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [info, setInfo] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);

  const id = employeeId.trim().toUpperCase();
  const passwordOk = next.trim().length >= MIN && /[A-Za-z]/.test(next) && /\d/.test(next) && next === confirm;

  async function sendCode() {
    setError(null);
    setBusy(true);
    try {
      const r = await request<{ message: string; available: boolean }>("/auth/forgot-password", {
        method: "POST", body: { employee_code: id }, noRefresh: true,
      });
      if (r.available) {
        setInfo(r.message);
        setStep("code");
      } else setError(r.message);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Couldn't send the code. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  async function reset() {
    setError(null);
    setBusy(true);
    try {
      await request("/auth/reset-with-code", {
        method: "POST", body: { employee_code: id, code: code.trim(), new_password: next }, noRefresh: true,
      });
      setDone(true);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Couldn't change the password. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Screen keyboard>
      <View style={{ gap: 16 }}>
        <Title sub={done ? undefined : step === "id" ? "We'll email a 6-digit code to the address saved on your account." : "Enter the code from your email and choose a new password."}>
          Reset your password
        </Title>

        {done ? (
          <>
            <Text style={{ color: colors.text, fontSize: 15, lineHeight: 22 }}>Your password was changed. Sign in with your new password.</Text>
            <Button title="Back to sign in" onPress={() => router.replace("/login")} />
          </>
        ) : step === "id" ? (
          <>
            <Field label="Employee ID" value={employeeId} onChangeText={setEmployeeId} autoCapitalize="characters" autoCorrect={false} editable={!busy} />
            {error ? <Text style={{ color: colors.danger }}>{error}</Text> : null}
            <Button title="Email me a code" onPress={sendCode} loading={busy} disabled={id.length < 3} />
          </>
        ) : (
          <>
            {info ? <Text style={{ color: colors.textMuted, lineHeight: 20 }}>{info}</Text> : null}
            <Field label="6-digit code" value={code} onChangeText={(v) => setCode(v.replace(/\D/g, "").slice(0, 6))} keyboardType="number-pad" autoComplete="one-time-code" editable={!busy} />
            <Field label="New password" value={next} onChangeText={setNext} secureTextEntry autoCapitalize="none" autoCorrect={false}
              hint={`At least ${MIN} characters, with a letter and a number.`} editable={!busy} />
            <Field label="Confirm new password" value={confirm} onChangeText={setConfirm} secureTextEntry autoCapitalize="none" autoCorrect={false}
              error={confirm.length > 0 && next !== confirm ? "The two passwords don't match." : null} editable={!busy} />
            {error ? <Text style={{ color: colors.danger }}>{error}</Text> : null}
            <Button title="Change password" onPress={reset} loading={busy} disabled={code.length !== 6 || !passwordOk} />
            <Button title="Send a new code" variant="ghost" onPress={sendCode} disabled={busy} />
          </>
        )}
        {!done ? <Button title="Back to sign in" variant="ghost" onPress={() => router.back()} /> : null}
      </View>
    </Screen>
  );
}
