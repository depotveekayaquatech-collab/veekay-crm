import { Text, View } from "react-native";
import { Card, Chips } from "@/components/ui";
import { useTheme, type ThemePref } from "@/lib/themeContext";
import { colors, font } from "@/theme";

/** Light, dark, or follow the phone. The choice is kept on this phone. */
export function AppearanceCard() {
  const { pref, setPref } = useTheme();
  return (
    <Card>
      <View style={{ gap: 10 }}>
        <Text style={{ fontSize: 15, fontWeight: "700", color: colors.text }}>Appearance</Text>
        <Chips<ThemePref>
          options={[{ label: "Match phone", value: "system" }, { label: "Light", value: "light" }, { label: "Dark", value: "dark" }]}
          value={pref}
          onChange={setPref}
        />
        <Text style={font.small}>Dark is easier on the eyes at night and saves battery on many phones.</Text>
      </View>
    </Card>
  );
}
