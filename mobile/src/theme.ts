/** Same palette as the Veekay web app, so the two feel like one product. */
export const colors = {
  brand50: "#EEF3FF",
  brand100: "#DDE7FF",
  brand200: "#BCCFFE",
  brand500: "#2F6FED",
  brand600: "#2559C9",
  brand700: "#1E46A0",
  brand800: "#1C3B82",
  aqua200: "#A7E3EC",
  aqua500: "#0E8EA4",
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
  success: "#1B7F5C",
  successSoft: "#E3F5EC",
  warning: "#A8620A",
  warningSoft: "#FDF1DC",
  danger: "#C62F3A",
  dangerSoft: "#FCE8EA",
  white: "#FFFFFF",
} as const;

export const radius = { sm: 8, md: 12, lg: 16, xl: 22, pill: 999 } as const;
export const space = { xs: 4, sm: 8, md: 12, lg: 16, xl: 24, xxl: 32 } as const;

export const font = {
  regular: undefined,
  title: { fontSize: 22, fontWeight: "700" as const, color: colors.text },
  h2: { fontSize: 16, fontWeight: "700" as const, color: colors.text },
  body: { fontSize: 15, color: colors.text },
  small: { fontSize: 13, color: colors.textMuted },
  tiny: { fontSize: 11, color: colors.textMuted },
};

export const shadow = {
  card: { shadowColor: "#0B1222", shadowOpacity: 0.06, shadowRadius: 8, shadowOffset: { width: 0, height: 2 }, elevation: 2 },
};
