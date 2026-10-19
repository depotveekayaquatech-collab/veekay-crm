/**
 * Same palette as the Veekay web app, so the two feel like one product, in a light and a dark version.
 *
 * `colors` is ONE shared object. `applyScheme()` rewrites its values and the root layout then remounts the screens, so every
 * `colors.x` read while rendering gives the current theme. Code that runs when a file is loaded (a top-level constant) would keep
 * the first theme for ever, so inside this app colours are always read inside a function or a component.
 */
export type Scheme = "light" | "dark";

export interface Palette {
  brand50: string; brand100: string; brand200: string; brand500: string; brand600: string; brand700: string; brand800: string;
  aqua200: string; aqua500: string; aquaSoft: string; aqua700: string;
  ink950: string; ink900: string; ink700: string;
  text: string; textMuted: string; textFaint: string;
  surface: string; surfaceSubtle: string; surfaceMuted: string; border: string;
  success: string; successSoft: string; warning: string; warningSoft: string; danger: string; dangerSoft: string;
  white: string;
}

export const lightPalette: Palette = {
  brand50: "#EEF3FF",
  brand100: "#DDE7FF",
  brand200: "#BCCFFE",
  brand500: "#2F6FED",
  brand600: "#2559C9",
  brand700: "#1E46A0",
  brand800: "#1C3B82",
  aqua200: "#A7E3EC",
  aqua500: "#0E8EA4",
  aquaSoft: "#DDF4F8",
  aqua700: "#0A6B7C",
  ink950: "#070C18",
  ink900: "#0B1222",
  ink700: "#1A2542",
  text: "#0B1222",
  textMuted: "#5B6478",
  textFaint: "#8A93A6",
  surface: "#FFFFFF",
  surfaceSubtle: "#F5F6FA",
  surfaceMuted: "#ECEEF4",
  border: "#E2E5EE",
  success: "#16704E",
  successSoft: "#E3F5EC",
  warning: "#8F5207",
  warningSoft: "#FDF1DC",
  danger: "#C62F3A",
  dangerSoft: "#FCE8EA",
  white: "#FFFFFF",
};

/** Deep navy rather than black, with the same blue as the light theme lifted a little so it reads on dark. */
export const darkPalette: Palette = {
  brand50: "#16264B",
  brand100: "#1D3266",
  brand200: "#2C4A92",
  brand500: "#5B8FF5",
  brand600: "#4A82F2",
  brand700: "#9DBBFF",
  brand800: "#C3D5FF",
  aqua200: "#12414C",
  aqua500: "#38C2D8",
  aquaSoft: "#0F3540",
  aqua700: "#6AD8EA",
  ink950: "#1B2745",
  ink900: "#16203A",
  ink700: "#27355C",
  text: "#E8ECF6",
  textMuted: "#A0AAC0",
  textFaint: "#7A859E",
  surface: "#121A2D",
  surfaceSubtle: "#0A0F1C",
  surfaceMuted: "#1B2540",
  border: "#27314A",
  success: "#45CF98",
  successSoft: "#0F3A2C",
  warning: "#F2AA55",
  warningSoft: "#3A2A0E",
  danger: "#F47983",
  dangerSoft: "#40191F",
  white: "#FFFFFF",
};

export const colors: Palette = { ...lightPalette };
let current: Scheme = "light";

/** Switch the shared colours. The caller re-renders the app (see the theme provider). */
export function applyScheme(scheme: Scheme): void {
  Object.assign(colors, scheme === "dark" ? darkPalette : lightPalette);
  current = scheme;
}

export const currentScheme = (): Scheme => current;

export const radius = { sm: 8, md: 12, lg: 16, xl: 22, pill: 999 } as const;
export const space = { xs: 4, sm: 8, md: 12, lg: 16, xl: 24, xxl: 32 } as const;

/** Text styles. Each read builds the style from the current colours. */
export const font = {
  regular: undefined,
  get title() { return { fontSize: 22, fontWeight: "700" as const, color: colors.text }; },
  get h2() { return { fontSize: 16, fontWeight: "700" as const, color: colors.text }; },
  get body() { return { fontSize: 15, color: colors.text }; },
  get small() { return { fontSize: 13, color: colors.textMuted }; },
  get tiny() { return { fontSize: 11, color: colors.textMuted }; },
};

export const shadow = {
  card: { shadowColor: "#0B1222", shadowOpacity: 0.06, shadowRadius: 8, shadowOffset: { width: 0, height: 2 }, elevation: 2 },
};

/**
 * The look of a "N days pending" pill: calm blue the day it is due, aqua at one day behind, amber at two, red from three, and a
 * solid red once a store is five or more days behind. Colours come from the theme so they suit both light and dark.
 */
export function pendingTone(days: number): { bg: string; fg: string; dot: string } {
  if (days <= 0) return { bg: colors.brand50, fg: colors.brand700, dot: colors.brand500 };
  if (days === 1) return { bg: colors.aquaSoft, fg: colors.aqua700, dot: colors.aqua500 };
  if (days === 2) return { bg: colors.warningSoft, fg: colors.warning, dot: colors.warning };
  if (days < 5) return { bg: colors.dangerSoft, fg: colors.danger, dot: colors.danger };
  return { bg: "#C62F3A", fg: "#FFFFFF", dot: "#FFFFFF" };      // a fixed deep red with white text reads on a light or a dark card
}

export function pendingLabel(days: number): string {
  return days <= 0 ? "Due today" : `${days} day${days === 1 ? "" : "s"} pending`;
}
