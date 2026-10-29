import { Pressable, Text, View } from "react-native";
import { colors, radius } from "@/theme";

export interface CellState {
  disabled?: boolean;
  selected?: boolean;
  /** Part of a range between two chosen dates (leave). */
  inRange?: boolean;
  /** Small text under the day number, for example a saved count. */
  badge?: string | number | null;
  /** Colour of the badge: done (green) by default; the entry tones come from the server (first entry, changed once, changed twice or more, Team Lead, admin). */
  badgeTone?: "done" | "muted" | "changed" | "l1_first" | "l1_second" | "l1_third" | "l2" | "admin";
  today?: boolean;
}

// The colour of an entry's number. Yellow is "changed once", so the administrator colour is violet (orange sits too close to red).
const TONE_COLOR: Record<string, string> = { l1_first: colors.success, l1_second: "#B7860B", l1_third: colors.danger, l2: "#2559C9", admin: "#7C3AED" };

const WEEK = ["M", "T", "W", "T", "F", "S", "S"];
const pad = (n: number) => String(n).padStart(2, "0");
export const isoOf = (y: number, m: number, d: number) => `${y}-${pad(m)}-${pad(d)}`;

/** A month as a tappable grid (like a calendar app). Weeks start on Monday. */
export function MonthGrid({
  year, month, state, onPress,
}: { year: number; month: number; state: (iso: string) => CellState; onPress: (iso: string) => void }) {
  const first = new Date(year, month - 1, 1);
  const lead = (first.getDay() + 6) % 7;                         // blanks before the 1st (Monday = 0)
  const count = new Date(year, month, 0).getDate();
  const cells: (number | null)[] = [...Array(lead).fill(null), ...Array.from({ length: count }, (_, i) => i + 1)];
  while (cells.length % 7) cells.push(null);

  return (
    <View>
      <View style={{ flexDirection: "row" }}>
        {WEEK.map((w, i) => (
          <Text key={i} style={{ width: `${100 / 7}%`, textAlign: "center", fontSize: 11, fontWeight: "700", color: colors.textFaint, paddingVertical: 6 }}>{w}</Text>
        ))}
      </View>
      <View style={{ flexDirection: "row", flexWrap: "wrap" }}>
        {cells.map((d, i) => {
          if (d === null) return <View key={i} style={{ width: `${100 / 7}%`, height: 56 }} />;
          const iso = isoOf(year, month, d);
          const s = state(iso);
          const bg = s.selected ? colors.brand600 : s.inRange ? colors.brand100 : undefined;
          const fg = s.selected ? colors.white : s.disabled ? colors.textFaint : colors.text;
          return (
            <View key={i} style={{ width: `${100 / 7}%`, height: 56, padding: 2 }}>
              <Pressable
                onPress={() => onPress(iso)}
                disabled={s.disabled}
                accessibilityRole="button"
                accessibilityState={{ selected: !!s.selected, disabled: !!s.disabled }}
                accessibilityLabel={`${d} ${first.toLocaleDateString("en-IN", { month: "long" })}${s.badge != null ? `, ${s.badge}` : ""}${s.today ? ", today" : ""}`}
                style={{
                  flex: 1, borderRadius: radius.md, alignItems: "center", justifyContent: "center", backgroundColor: bg,
                  borderWidth: s.today && !s.selected ? 1.5 : 0, borderColor: colors.brand600,
                }}
              >
                <Text style={{ fontSize: 15, fontWeight: s.selected || s.today ? "800" : "600", color: fg }}>{d}</Text>
                {s.badge != null ? (
                  <Text style={{ fontSize: 10, fontWeight: "700", marginTop: 1, color: s.selected ? colors.white : s.badgeTone === "muted" ? colors.textFaint : s.badgeTone === "changed" ? colors.warning : (s.badgeTone && TONE_COLOR[s.badgeTone]) || colors.success }}>{s.badge}</Text>
                ) : null}
              </Pressable>
            </View>
          );
        })}
      </View>
    </View>
  );
}
