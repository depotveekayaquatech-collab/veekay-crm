import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { Appearance } from "react-native";
import AsyncStorage from "@react-native-async-storage/async-storage";
import * as SystemUI from "expo-system-ui";
import { StatusBar } from "expo-status-bar";
import { applyScheme, colors, currentScheme, type Scheme } from "@/theme";

export type ThemePref = "system" | "light" | "dark";
const KEY = "veekay.theme";

interface ThemeValue {
  /** What the person chose: follow the phone, or always light / dark. */
  pref: ThemePref;
  /** What is showing now. */
  scheme: Scheme;
  setPref: (p: ThemePref) => void;
  /** Changes every time the colours change; the screens are remounted under it so none keeps the old colours. */
  version: number;
}

const ThemeContext = createContext<ThemeValue>({ pref: "system", scheme: "light", setPref: () => undefined, version: 0 });
export const useTheme = () => useContext(ThemeContext);

function resolve(pref: ThemePref): Scheme {
  if (pref === "system") return Appearance.getColorScheme() === "dark" ? "dark" : "light";
  return pref;
}

function paintRoot() {
  // the colour behind everything (over-scroll, keyboard resize, screen transitions), so no white flash in the dark theme
  void SystemUI.setBackgroundColorAsync(colors.surfaceSubtle).catch(() => undefined);
}

/** Holds the person's theme choice (kept on the phone), applies it before the first screen is drawn, and follows the phone's
 * light / dark setting while the choice is "system". */
export function ThemeProvider({ children }: { children: ReactNode }) {
  const [pref, setPrefState] = useState<ThemePref>("system");
  const [ready, setReady] = useState(false);
  const [version, setVersion] = useState(0);

  const change = useCallback((p: ThemePref) => {
    const next = resolve(p);
    if (next !== currentScheme()) {
      applyScheme(next);
      paintRoot();
      setVersion((v) => v + 1);
    }
  }, []);

  useEffect(() => {
    let alive = true;
    (async () => {
      let saved: ThemePref = "system";
      try {
        const v = await AsyncStorage.getItem(KEY);
        if (v === "light" || v === "dark" || v === "system") saved = v;
      } catch { /* no stored choice: follow the phone */ }
      if (!alive) return;
      applyScheme(resolve(saved));
      paintRoot();
      setPrefState(saved);
      setReady(true);
    })();
    return () => { alive = false; };
  }, []);

  useEffect(() => {
    if (pref !== "system") return;
    const sub = Appearance.addChangeListener(() => change("system"));
    return () => sub.remove();
  }, [pref, change]);

  const setPref = useCallback((p: ThemePref) => {
    setPrefState(p);
    AsyncStorage.setItem(KEY, p).catch(() => undefined);
    change(p);
  }, [change]);

  const value = useMemo<ThemeValue>(() => ({ pref, scheme: currentScheme(), setPref, version }), [pref, setPref, version]);
  // nothing is drawn until the choice is known, so the first screen is never shown in the wrong theme
  if (!ready) return null;
  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

/** Remounts what is inside whenever the colours change, so every screen reads the new colours. Put it inside the providers that
 * must keep their state (sign-in, data cache). */
export function ThemeBoundary({ children }: { children: ReactNode }) {
  const { version } = useTheme();
  return <ThemeKeyed key={version}>{children}</ThemeKeyed>;
}

function ThemeKeyed({ children }: { children: ReactNode }) {
  return <>{children}</>;
}

export function ThemedStatusBar() {
  const { scheme } = useTheme();
  return <StatusBar style={scheme === "dark" ? "light" : "dark"} />;
}
