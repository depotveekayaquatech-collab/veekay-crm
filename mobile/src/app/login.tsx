import { useRef, useState } from "react";
import { Image, KeyboardAvoidingView, Linking, Platform, Pressable, ScrollView, Text, TextInput, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import Constants from "expo-constants";
import { useRouter } from "expo-router";
import { StatusBar } from "expo-status-bar";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useAuth } from "@/auth/AuthProvider";
import { Button, Field } from "@/components/ui";
import { colors, radius } from "@/theme";

const extra = (Constants.expoConfig?.extra ?? {}) as { privacyPolicyUrl?: string; supportEmail?: string; supportPhone?: string };
const EMAIL_OK = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
// An email is a vendor / POC login; anything else is a Veekay Employee ID (like EMP001).
const loginOk = (v: string) => (v.includes("@") ? EMAIL_OK.test(v.trim()) : /^[A-Za-z0-9._-]{3,32}$/.test(v.trim()));

export default function LoginScreen() {
  const { signIn } = useAuth();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const passwordRef = useRef<TextInput>(null);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [show, setShow] = useState(false);
  const [touched, setTouched] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const emailError = touched && !loginOk(email) ? "Enter your email, or your Employee ID" : null;
  const passwordError = touched && !password ? "Enter your password" : null;

  async function submit() {
    setTouched(true);
    setError(null);
    if (!loginOk(email) || !password) return;
    setBusy(true);
    try {
      await signIn(email, password);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't sign in. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  const helpLines = [
    extra.supportPhone ? { icon: "call-outline" as const, text: extra.supportPhone, url: `tel:${extra.supportPhone}` } : null,
    extra.supportEmail ? { icon: "mail-outline" as const, text: extra.supportEmail, url: `mailto:${extra.supportEmail}` } : null,
  ].filter(<T,>(x: T | null): x is T => x !== null);

  return (
    <KeyboardAvoidingView style={{ flex: 1, backgroundColor: colors.ink950 }} behavior={Platform.OS === "ios" ? "padding" : undefined}>
      <StatusBar style="light" />
      <ScrollView
        keyboardShouldPersistTaps="handled"
        contentContainerStyle={{ flexGrow: 1 }}
        showsVerticalScrollIndicator={false}
        automaticallyAdjustKeyboardInsets
      >
        {/* Brand header */}
        <View style={{ paddingTop: insets.top + 36, paddingBottom: 56, paddingHorizontal: 28, overflow: "hidden" }}>
          <View style={{ position: "absolute", top: -90, left: -70, width: 260, height: 260, borderRadius: 130, backgroundColor: colors.brand500, opacity: 0.45 }} />
          <View style={{ position: "absolute", bottom: -110, right: -60, width: 240, height: 240, borderRadius: 120, backgroundColor: colors.aqua500, opacity: 0.4 }} />
          <View style={{ alignSelf: "flex-start", backgroundColor: colors.white, borderRadius: radius.lg, paddingHorizontal: 14, paddingVertical: 10 }}>
            <Image source={require("../../assets/watr-logo.png")} style={{ width: 84, height: 48 }} resizeMode="contain" accessibilityLabel="WaTR" />
          </View>
          <Text style={{ marginTop: 28, fontSize: 30, fontWeight: "800", color: colors.white, letterSpacing: -0.5 }} accessibilityRole="header">
            Veekay Partner
          </Text>
          <Text style={{ marginTop: 6, fontSize: 15, lineHeight: 22, color: "rgba(255,255,255,0.72)" }}>
            Orders, deliveries and tickets for your stores, in one place.
          </Text>
        </View>

        {/* Form sheet */}
        <View style={{ flex: 1, backgroundColor: colors.surface, borderTopLeftRadius: 28, borderTopRightRadius: 28, marginTop: -28, paddingHorizontal: 24, paddingTop: 28, paddingBottom: insets.bottom + 20 }}>
          <Text style={{ fontSize: 22, fontWeight: "700", color: colors.text }}>Sign in</Text>
          <Text style={{ marginTop: 4, marginBottom: 22, fontSize: 14, color: colors.textMuted }}>Vendors and POCs use their email. Veekay employees use their Employee ID.</Text>

          <View style={{ gap: 16 }}>
            <Field
              label="Email or Employee ID"
              value={email}
              onChangeText={setEmail}
              keyboardType="default"
              autoCapitalize="none"
              autoCorrect={false}
              autoComplete="username"
              textContentType="username"
              returnKeyType="next"
              onSubmitEditing={() => passwordRef.current?.focus()}
              error={emailError}
              editable={!busy}
              left={<Ionicons name="person-outline" size={18} color={colors.textFaint} />}
            />
            <Field
              ref={passwordRef}
              label="Password"
              value={password}
              onChangeText={setPassword}
              placeholder="Your password"
              secureTextEntry={!show}
              autoCapitalize="none"
              autoCorrect={false}
              autoComplete="password"
              textContentType="password"
              returnKeyType="go"
              onSubmitEditing={submit}
              error={passwordError}
              editable={!busy}
              left={<Ionicons name="lock-closed-outline" size={18} color={colors.textFaint} />}
              right={
                <Pressable onPress={() => setShow((v) => !v)} hitSlop={10} accessibilityRole="button" accessibilityLabel={show ? "Hide password" : "Show password"} style={{ paddingLeft: 8 }}>
                  <Ionicons name={show ? "eye-off-outline" : "eye-outline"} size={22} color={colors.textMuted} />
                </Pressable>
              }
            />
          </View>

          {error ? (
            <View accessibilityRole="alert" style={{ marginTop: 16, flexDirection: "row", gap: 8, alignItems: "flex-start", padding: 12, borderRadius: radius.md, backgroundColor: colors.dangerSoft }}>
              <Ionicons name="alert-circle" size={18} color={colors.danger} style={{ marginTop: 1 }} />
              <Text style={{ flex: 1, color: colors.danger, fontSize: 14, lineHeight: 20 }}>{error}</Text>
            </View>
          ) : null}

          <Button title="Sign in" onPress={submit} loading={busy} style={{ marginTop: 22, minHeight: 54 }} />
          <Button title="Forgot your password?" variant="ghost" onPress={() => router.push("/forgot-password" as never)} style={{ marginTop: 8 }} />

          <View style={{ marginTop: 28, padding: 14, borderRadius: radius.md, backgroundColor: colors.surfaceSubtle, gap: 8 }}>
            <Text style={{ fontSize: 13, fontWeight: "700", color: colors.text }}>Forgot your password or can't sign in?</Text>
            <Text style={{ fontSize: 13, lineHeight: 19, color: colors.textMuted }}>Your Veekay contact can reset it for you.</Text>
            {helpLines.map((l) => (
              <Pressable key={l.url} onPress={() => Linking.openURL(l.url)} accessibilityRole="link" style={{ flexDirection: "row", alignItems: "center", gap: 8, minHeight: 32 }}>
                <Ionicons name={l.icon} size={16} color={colors.brand600} />
                <Text style={{ color: colors.brand600, fontWeight: "600", fontSize: 14 }}>{l.text}</Text>
              </Pressable>
            ))}
          </View>

          <View style={{ marginTop: 24, alignItems: "center", gap: 6 }}>
            {extra.privacyPolicyUrl ? (
              <Pressable onPress={() => Linking.openURL(extra.privacyPolicyUrl!)} accessibilityRole="link" hitSlop={8}>
                <Text style={{ fontSize: 13, color: colors.textMuted, textDecorationLine: "underline" }}>Privacy policy</Text>
              </Pressable>
            ) : null}
            <Text style={{ fontSize: 12, color: colors.textFaint }}>Version {Constants.expoConfig?.version ?? "1.0.0"}</Text>
          </View>
        </View>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}
