import { forwardRef, useState, type ReactNode } from "react";
import {
  ActivityIndicator, Animated, Easing, KeyboardAvoidingView, Platform, Pressable, RefreshControl, ScrollView, StyleSheet,
  Text, TextInput, View, type StyleProp, type TextInputProps, type ViewStyle,
} from "react-native";
import { useEffect } from "react";
import { Ionicons } from "@expo/vector-icons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { isConnectivityMessage } from "@/lib/connectivityCore";
import { colors, currentScheme, font, radius, shadow, space } from "@/theme";
import type { Outcome, TicketStatus } from "@/api/api";
import { titleCase } from "@/lib/format";

/** Scrollable screen with pull-to-refresh, keyboard handling and safe-area padding. */
export function Screen({
  children, onRefresh, refreshing = false, padBottom = space.xxl, keyboard = false, style,
}: {
  children: ReactNode; onRefresh?: () => void; refreshing?: boolean; padBottom?: number; keyboard?: boolean; style?: StyleProp<ViewStyle>;
}) {
  const insets = useSafeAreaInsets();
  const body = (
    <ScrollView
      style={{ flex: 1, backgroundColor: colors.surfaceSubtle }}
      contentContainerStyle={[{ padding: space.lg, paddingBottom: padBottom + insets.bottom }, style]}
      keyboardShouldPersistTaps="handled"
      refreshControl={onRefresh ? <RefreshControl refreshing={refreshing} onRefresh={onRefresh} colors={[colors.brand600]} /> : undefined}
    >
      {children}
    </ScrollView>
  );
  return keyboard ? <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === "ios" ? "padding" : "height"}>{body}</KeyboardAvoidingView> : body;
}

export function Title({ children, sub }: { children: ReactNode; sub?: string }) {
  return (
    <View style={{ marginBottom: space.lg }}>
      <Text style={font.title} accessibilityRole="header">{children}</Text>
      {sub ? <Text style={[font.small, { marginTop: 2 }]}>{sub}</Text> : null}
    </View>
  );
}

export function SectionTitle({ children, action }: { children: ReactNode; action?: ReactNode }) {
  return (
    <View style={s.sectionRow}>
      <Text style={font.h2} accessibilityRole="header">{children}</Text>
      {action}
    </View>
  );
}

export function Card({ children, style, onPress, label }: { children: ReactNode; style?: StyleProp<ViewStyle>; onPress?: () => void; label?: string }) {
  if (!onPress) return <View style={[s.card, style]}>{children}</View>;
  return (
    <Pressable
      onPress={onPress}
      accessibilityRole="button"
      accessibilityLabel={label}
      android_ripple={{ color: colors.brand100 }}
      style={({ pressed }) => [s.card, style, pressed && Platform.OS === "ios" && { opacity: 0.7 }]}
    >
      {children}
    </Pressable>
  );
}

type Variant = "primary" | "secondary" | "danger" | "ghost";

export function Button({
  title, onPress, variant = "primary", loading, disabled, icon, style,
}: { title: string; onPress: () => void; variant?: Variant; loading?: boolean; disabled?: boolean; icon?: ReactNode; style?: StyleProp<ViewStyle> }) {
  const off = disabled || loading;
  const bg = variant === "primary" ? colors.brand600 : variant === "danger" ? colors.danger : variant === "secondary" ? colors.surface : "transparent";
  const fg = variant === "primary" || variant === "danger" ? colors.white : variant === "secondary" ? colors.brand700 : colors.brand600;
  return (
    <Pressable
      onPress={onPress}
      disabled={off}
      accessibilityRole="button"
      accessibilityState={{ disabled: !!off, busy: !!loading }}
      android_ripple={{ color: "rgba(255,255,255,0.25)" }}
      style={({ pressed }) => [
        s.button, { backgroundColor: bg, opacity: off ? 0.5 : pressed ? 0.85 : 1 },
        variant === "secondary" && { borderWidth: 1.5, borderColor: colors.brand600 }, style,
      ]}
    >
      {loading ? <ActivityIndicator color={fg} /> : (
        <View style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
          {icon}
          <Text style={[s.buttonText, { color: fg }]}>{title}</Text>
        </View>
      )}
    </Pressable>
  );
}

export const Field = forwardRef<TextInput, TextInputProps & { label: string; error?: string | null; hint?: string; left?: ReactNode; right?: ReactNode }>(
  function Field({ label, error, hint, left, right, ...rest }, ref) {
    const [focused, setFocused] = useState(false);
    return (
      <View style={{ gap: 6 }}>
        <Text style={s.label}>{label}</Text>
        <View style={[s.inputWrap, focused && { borderColor: colors.brand500 }, error ? { borderColor: colors.danger } : null]}>
          {left ? <View style={{ marginRight: 10 }}>{left}</View> : null}
          <TextInput
            ref={ref}
            placeholderTextColor={colors.textFaint}
            accessibilityLabel={label}
            style={[s.input, rest.multiline && { minHeight: 96, textAlignVertical: "top", paddingTop: 12 }]}
            {...rest}
            onFocus={(e) => { setFocused(true); rest.onFocus?.(e); }}
            onBlur={(e) => { setFocused(false); rest.onBlur?.(e); }}
          />
          {right}
        </View>
        {error ? <Text style={{ color: colors.danger, fontSize: 13 }}>{error}</Text> : hint ? <Text style={font.tiny}>{hint}</Text> : null}
      </View>
    );
  },
);

type ToneName = "success" | "warning" | "danger" | "info" | "neutral";
const tones = (): Record<ToneName, readonly [string, string]> => ({
  success: [colors.successSoft, colors.success], warning: [colors.warningSoft, colors.warning], danger: [colors.dangerSoft, colors.danger],
  info: [colors.brand50, colors.brand700], neutral: [colors.surfaceMuted, colors.textMuted],
});

export function Badge({ children, tone = "neutral" }: { children: ReactNode; tone?: ToneName }) {
  const [bg, fg] = tones()[tone];
  return (
    <View style={[s.badge, { backgroundColor: bg }]}>
      <Text style={{ color: fg, fontSize: 12, fontWeight: "700" }}>{children}</Text>
    </View>
  );
}

const STATUS_TONE: Record<TicketStatus, ToneName> = { OPEN: "warning", IN_PROGRESS: "info", RESOLVED: "success", CLOSED: "neutral" };
export const TicketStatusBadge = ({ status }: { status: TicketStatus }) => <Badge tone={STATUS_TONE[status]}>{titleCase(status)}</Badge>;
export const OutcomeBadge = ({ outcome }: { outcome: Outcome }) => (
  <Badge tone={outcome === "RECEIVED" ? "success" : outcome === "SHORT" ? "warning" : "danger"}>{titleCase(outcome)}</Badge>
);

export function Chips<T extends string>({ options, value, onChange }: { options: { label: string; value: T }[]; value: T; onChange: (v: T) => void }) {
  return (
    <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 8 }} accessibilityRole="tablist">
      {options.map((o) => {
        const on = o.value === value;
        return (
          <Pressable
            key={o.value}
            onPress={() => onChange(o.value)}
            accessibilityRole="tab"
            accessibilityState={{ selected: on }}
            style={[s.chip, on && { backgroundColor: colors.brand600, borderColor: colors.brand600 }]}
          >
            <Text style={{ fontSize: 14, fontWeight: "600", color: on ? colors.white : colors.textMuted }}>{o.label}</Text>
          </Pressable>
        );
      })}
    </ScrollView>
  );
}

export function Empty({ title, text, action, icon }: { title: string; text?: string; action?: ReactNode; icon?: React.ComponentProps<typeof Ionicons>["name"] }) {
  return (
    <View style={s.empty}>
      {icon ? (
        <View style={{ width: 56, height: 56, borderRadius: 28, backgroundColor: colors.brand50, alignItems: "center", justifyContent: "center", marginBottom: space.md }}>
          <Ionicons name={icon} size={28} color={colors.brand600} />
        </View>
      ) : null}
      <Text style={[font.h2, { textAlign: "center" }]}>{title}</Text>
      {text ? <Text style={[font.small, { textAlign: "center", marginTop: 4 }]}>{text}</Text> : null}
      {action ? <View style={{ marginTop: space.lg }}>{action}</View> : null}
    </View>
  );
}

export function ErrorNote({ message, onRetry }: { message: string; onRetry?: () => void }) {
  // Connection problems are announced once by the global banner; each list only says it could not load.
  if (isConnectivityMessage(message)) message = "Couldn't load this right now.";
  return (
    <View style={s.error} accessibilityRole="alert">
      <Text style={{ color: colors.danger, flex: 1, fontSize: 14 }}>{message}</Text>
      {onRetry ? <Pressable onPress={onRetry} accessibilityRole="button" hitSlop={8}><Text style={{ color: colors.danger, fontWeight: "700" }}>Retry</Text></Pressable> : null}
    </View>
  );
}

export function Skeleton({ height = 64 }: { height?: number }) {
  const [o] = useState(() => new Animated.Value(0.45));
  useEffect(() => {
    const loop = Animated.loop(Animated.sequence([
      Animated.timing(o, { toValue: 1, duration: 700, easing: Easing.inOut(Easing.ease), useNativeDriver: true }),
      Animated.timing(o, { toValue: 0.45, duration: 700, easing: Easing.inOut(Easing.ease), useNativeDriver: true }),
    ]));
    loop.start();
    return () => loop.stop();
  }, [o]);
  return <Animated.View style={{ height, borderRadius: radius.lg, backgroundColor: colors.surfaceMuted, opacity: o, marginBottom: 8 }} />;
}

export function ListSkeleton({ rows = 4 }: { rows?: number }) {
  return <View accessibilityLabel="Loading">{Array.from({ length: rows }, (_, i) => <Skeleton key={i} />)}</View>;
}

/** A thin progress bar. `value` is 0..1; it announces its percentage to screen readers. */
export function ProgressBar({ value, tone = "brand" }: { value: number; tone?: "brand" | "success" | "warning" | "danger" }) {
  const pct = Math.round(Math.max(0, Math.min(1, value)) * 100);
  const fill = tone === "success" ? colors.success : tone === "danger" ? colors.danger : tone === "warning" ? "#D9A400" : colors.brand500;
  return (
    <View
      accessibilityRole="progressbar"
      accessibilityValue={{ min: 0, max: 100, now: pct }}
      style={{ height: 8, borderRadius: 4, backgroundColor: colors.surfaceMuted, overflow: "hidden" }}
    >
      <View style={{ height: 8, borderRadius: 4, width: `${pct}%`, backgroundColor: fill }} />
    </View>
  );
}

export function Pager({ page, pageSize, total, onPage }: { page: number; pageSize: number; total: number; onPage: (p: number) => void }) {
  const pages = Math.max(1, Math.ceil(total / pageSize));
  if (pages <= 1) return null;
  return (
    <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginTop: space.md }}>
      <Button title="Previous" variant="ghost" disabled={page <= 1} onPress={() => onPage(page - 1)} style={{ minWidth: 100 }} />
      <Text style={font.small}>Page {page} of {pages}</Text>
      <Button title="Next" variant="ghost" disabled={page >= pages} onPress={() => onPage(page + 1)} style={{ minWidth: 100 }} />
    </View>
  );
}

/** Styles built from the current colours: rebuilt (once) when the theme changes. */
function lazyStyles<T extends Record<string, object>>(make: () => T): T {
  let scheme = currentScheme();
  let cache = make();
  const out = {} as T;
  for (const key of Object.keys(cache) as (keyof T)[]) {
    Object.defineProperty(out, key, {
      enumerable: true,
      get: () => {
        if (scheme !== currentScheme()) { scheme = currentScheme(); cache = make(); }
        return cache[key];
      },
    });
  }
  return out;
}

const s = lazyStyles(() => StyleSheet.create({
  sectionRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginTop: space.xl, marginBottom: space.sm },
  card: { backgroundColor: colors.surface, borderRadius: radius.lg, borderWidth: StyleSheet.hairlineWidth, borderColor: colors.border, padding: space.lg, ...shadow.card },
  button: { minHeight: 52, borderRadius: radius.md, paddingHorizontal: space.xl, alignItems: "center", justifyContent: "center" },
  buttonText: { fontSize: 16, fontWeight: "700" },
  label: { fontSize: 13, fontWeight: "600", color: colors.text },
  inputWrap: { flexDirection: "row", alignItems: "center", minHeight: 52, borderRadius: radius.md, borderWidth: 1.5, borderColor: colors.border, backgroundColor: colors.surface, paddingHorizontal: 14 },
  input: { flex: 1, fontSize: 16, color: colors.text, paddingVertical: 12 },
  badge: { alignSelf: "flex-start", borderRadius: radius.pill, paddingHorizontal: 10, paddingVertical: 3 },
  chip: { minHeight: 44, paddingHorizontal: 16, borderRadius: radius.pill, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface, alignItems: "center", justifyContent: "center" },
  empty: { alignItems: "center", justifyContent: "center", paddingVertical: 48, paddingHorizontal: 24, borderRadius: radius.lg, borderWidth: 1, borderStyle: "dashed", borderColor: colors.border },
  error: { flexDirection: "row", alignItems: "center", gap: 12, padding: space.md, borderRadius: radius.md, backgroundColor: colors.dangerSoft },
}));
