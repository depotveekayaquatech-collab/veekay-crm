/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        // Brand — the only accent colour in the product.
        brand: {
          50: "rgb(var(--brand-50) / <alpha-value>)", 100: "rgb(var(--brand-100) / <alpha-value>)", 200: "rgb(var(--brand-200) / <alpha-value>)", 300: "rgb(var(--brand-300) / <alpha-value>)", 400: "rgb(var(--brand-400) / <alpha-value>)", 500: "rgb(var(--brand-500) / <alpha-value>)", 600: "rgb(var(--brand-600) / <alpha-value>)", 700: "rgb(var(--brand-700) / <alpha-value>)", 800: "rgb(var(--brand-800) / <alpha-value>)", 900: "rgb(var(--brand-900) / <alpha-value>)",
        },
        // Secondary accent — water/teal. Used sparingly: tiles, highlights, success-adjacent UI.
        aqua: {
          50: "rgb(var(--aqua-50) / <alpha-value>)", 100: "rgb(var(--aqua-100) / <alpha-value>)", 200: "rgb(var(--aqua-200) / <alpha-value>)", 300: "rgb(var(--aqua-300) / <alpha-value>)", 400: "rgb(var(--aqua-400) / <alpha-value>)", 500: "rgb(var(--aqua-500) / <alpha-value>)", 600: "rgb(var(--aqua-600) / <alpha-value>)", 700: "rgb(var(--aqua-700) / <alpha-value>)",
        },
        // Neutrals — every gray-* utility resolves to this ink-tinted scale (inverted in dark mode).
        gray: {
          50: "rgb(var(--gray-50) / <alpha-value>)", 100: "rgb(var(--gray-100) / <alpha-value>)", 200: "rgb(var(--gray-200) / <alpha-value>)", 300: "rgb(var(--gray-300) / <alpha-value>)", 400: "rgb(var(--gray-400) / <alpha-value>)", 500: "rgb(var(--gray-500) / <alpha-value>)", 600: "rgb(var(--gray-600) / <alpha-value>)", 700: "rgb(var(--gray-700) / <alpha-value>)", 800: "rgb(var(--gray-800) / <alpha-value>)", 900: "rgb(var(--gray-900) / <alpha-value>)",
        },
        // Deep navy for the sidebar / dark surfaces (the same in both themes).
        ink: { 950: "#070c18", 900: "#0b1222", 800: "#111a30", 700: "#1a2542", 600: "#26345a" },
        // Headings: dark navy on light, near-white on dark.
        heading: "rgb(var(--heading) / <alpha-value>)",
        surface: { DEFAULT: "rgb(var(--surface) / <alpha-value>)", subtle: "rgb(var(--surface-subtle) / <alpha-value>)", muted: "rgb(var(--surface-muted) / <alpha-value>)", border: "rgb(var(--surface-border) / <alpha-value>)" },
        // Semantic status colours (info intentionally reuses the brand blue).
        status: {
          success: "rgb(var(--success) / <alpha-value>)", "success-soft": "rgb(var(--success-soft) / <alpha-value>)",
          warning: "rgb(var(--warning) / <alpha-value>)", "warning-soft": "rgb(var(--warning-soft) / <alpha-value>)",
          danger: "rgb(var(--danger) / <alpha-value>)", "danger-soft": "rgb(var(--danger-soft) / <alpha-value>)",
          info: "rgb(var(--info) / <alpha-value>)", "info-soft": "rgb(var(--info-soft) / <alpha-value>)",
          neutral: "rgb(var(--neutral) / <alpha-value>)",
        },
      },
      borderRadius: { sm: "6px", md: "8px", lg: "12px", xl: "16px" },
      fontFamily: {
        sans: [
          '"Plus Jakarta Sans"',
          "system-ui",
          "-apple-system",
          "Segoe UI",
          "Roboto",
          "Helvetica Neue",
          "sans-serif",
        ],
      },
      boxShadow: {
        sm: "0 1px 2px 0 rgba(11, 18, 34, 0.05)",
        card: "0 1px 2px rgba(11, 18, 34, 0.04), 0 4px 16px -6px rgba(11, 18, 34, 0.08)",
        md: "0 6px 16px -4px rgba(11, 18, 34, 0.12), 0 2px 6px -2px rgba(11, 18, 34, 0.06)",
        lg: "0 20px 44px -12px rgba(11, 18, 34, 0.28)",
        glow: "0 8px 22px -6px rgba(47, 111, 237, 0.55)",
        focus: "0 0 0 3px rgba(47, 111, 237, 0.20)",
      },
      keyframes: {
        "fade-in": { from: { opacity: "0" }, to: { opacity: "1" } },
        "slide-up": {
          from: { opacity: "0", transform: "translateY(6px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
      },
      animation: {
        "fade-in": "fade-in 0.2s ease-out",
        "slide-up": "slide-up 0.24s cubic-bezier(0.16, 1, 0.3, 1)",
      },
    },
  },
  plugins: [],
};
