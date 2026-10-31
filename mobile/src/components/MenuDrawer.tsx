import { useEffect, useRef, useState } from "react";
import { Animated, Easing, Modal, Pressable, ScrollView, Text, View, useWindowDimensions } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { usePathname, useRouter, type Href } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { colors, font, radius } from "@/theme";

type IconName = React.ComponentProps<typeof Ionicons>["name"];

export interface MenuItem {
  key: string;
  label: string;
  icon: IconName;
  href: Href;
  /** The path expo-router reports while this item's screen is open, to highlight it. */
  path: string;
  badge?: number;
}

export interface MenuSection {
  title?: string;
  items: MenuItem[];
}

/**
 * The side menu opened by the three-line button in the header: every screen of the app in one list.
 * Built from plain React Native pieces (a Modal and an Animated panel), so it adds no native library.
 */
export function MenuDrawer({ open, onClose, sections, who }: { open: boolean; onClose: () => void; sections: MenuSection[]; who: { name: string; code: string } }) {
  const router = useRouter();
  const pathname = usePathname();
  const insets = useSafeAreaInsets();
  const { width } = useWindowDimensions();
  const panelWidth = Math.min(320, Math.round(width * 0.82));
  const slide = useRef(new Animated.Value(0)).current;
  const [mounted, setMounted] = useState(open);

  useEffect(() => {
    if (open) {
      setMounted(true);
      Animated.timing(slide, { toValue: 1, duration: 220, easing: Easing.out(Easing.cubic), useNativeDriver: true }).start();
    } else {
      Animated.timing(slide, { toValue: 0, duration: 180, easing: Easing.in(Easing.cubic), useNativeDriver: true }).start(({ finished }) => {
        if (finished) setMounted(false);
      });
    }
  }, [open, slide]);

  if (!mounted) return null;

  function go(item: MenuItem) {
    onClose();
    // the tab screens are switched to; the others open on top
    router.navigate(item.href);
  }

  return (
    <Modal visible transparent animationType="none" onRequestClose={onClose} statusBarTranslucent>
      <View style={{ flex: 1, flexDirection: "row" }}>
        <Animated.View
          accessibilityViewIsModal
          style={{
            width: panelWidth, backgroundColor: colors.surface, paddingTop: insets.top, paddingBottom: insets.bottom,
            transform: [{ translateX: slide.interpolate({ inputRange: [0, 1], outputRange: [-panelWidth, 0] }) }],
          }}
        >
          <View style={{ paddingHorizontal: 20, paddingVertical: 18, borderBottomWidth: 1, borderBottomColor: colors.border, flexDirection: "row", alignItems: "center", gap: 12 }}>
            <View style={{ width: 46, height: 46, borderRadius: 23, backgroundColor: colors.brand600, alignItems: "center", justifyContent: "center", borderWidth: 2, borderColor: colors.brand100 }}>
              <Text style={{ color: colors.white, fontSize: 18, fontWeight: "800" }}>{(who.name.trim().slice(0, 1) || "?").toUpperCase()}</Text>
            </View>
            <View style={{ flex: 1 }}>
              <Text style={{ fontSize: 20, fontWeight: "800", color: colors.brand700 }}>Veekay</Text>
              <Text numberOfLines={1} style={[font.small, { marginTop: 1 }]}>{who.name} · {who.code}</Text>
            </View>
          </View>
          <ScrollView contentContainerStyle={{ paddingVertical: 8 }}>
            {sections.map((s, i) => (
              <View key={s.title ?? i} style={{ paddingTop: i === 0 ? 4 : 14 }}>
                {s.title ? <Text style={{ paddingHorizontal: 20, paddingBottom: 6, fontSize: 12, fontWeight: "700", color: colors.textFaint }}>{s.title}</Text> : null}
                {s.items.map((it) => {
                  const active = pathname === it.path;
                  return (
                    <Pressable
                      key={it.key}
                      onPress={() => go(it)}
                      accessibilityRole="button"
                      accessibilityState={{ selected: active }}
                      accessibilityLabel={it.badge ? `${it.label}, ${it.badge} waiting` : it.label}
                      android_ripple={{ color: colors.brand100 }}
                      style={({ pressed }) => ({ marginHorizontal: 10, marginVertical: 1, minHeight: 50, flexDirection: "row", alignItems: "center", gap: 14, paddingHorizontal: 12, borderRadius: radius.md, backgroundColor: active ? colors.brand50 : pressed ? colors.surfaceSubtle : "transparent" })}
                    >
                      {active ? <View style={{ position: "absolute", left: 0, top: 12, bottom: 12, width: 4, borderRadius: 2, backgroundColor: colors.brand600 }} /> : null}
                      <Ionicons name={it.icon} size={22} color={active ? colors.brand600 : colors.textMuted} />
                      <Text style={{ flex: 1, fontSize: 16, fontWeight: active ? "800" : "600", color: active ? colors.brand700 : colors.text }}>{it.label}</Text>
                      {it.badge ? (
                        <View style={{ minWidth: 22, height: 22, borderRadius: 11, paddingHorizontal: 6, backgroundColor: colors.warning, alignItems: "center", justifyContent: "center" }}>
                          <Text style={{ color: colors.white, fontSize: 12, fontWeight: "800" }}>{it.badge > 99 ? "99+" : it.badge}</Text>
                        </View>
                      ) : null}
                    </Pressable>
                  );
                })}
              </View>
            ))}
          </ScrollView>
        </Animated.View>
        <Animated.View style={{ flex: 1, opacity: slide.interpolate({ inputRange: [0, 1], outputRange: [0, 1] }), backgroundColor: "rgba(7,12,24,0.5)" }}>
          <Pressable style={{ flex: 1 }} onPress={onClose} accessibilityRole="button" accessibilityLabel="Close menu" />
        </Animated.View>
      </View>
    </Modal>
  );
}
