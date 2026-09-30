/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        // Brand — the only accent colour in the product.
        brand: {
          50: "#eef3ff", 100: "#dde7ff", 200: "#bccffe", 300: "#8fb0fc", 400: "#5b88f6",
          500: "#2f6fed", 600: "#2559c9", 700: "#1e46a0", 800: "#1c3b82", 900: "#1a336a",
        },
        // Secondary accent — water/teal. Used sparingly: tiles, highlights, success-adjacent UI.
        aqua: {
          50: "#e7f7fa", 100: "#c6edf2", 200: "#94dbe6", 300: "#5cc4d4", 400: "#2aa9bd",
          500: "#0e8ea4", 600: "#0b7285", 700: "#0a5b6a",
        },
        // Neutrals — every gray-* utility resolves to this ink-tinted scale.
        gray: {
          50: "#f7f8fc", 100: "#eef0f6", 200: "#e2e5ee", 300: "#c9cedc", 400: "#98a0b5",
          500: "#687189", 600: "#4b546c", 700: "#343c53", 800: "#1e2640", 900: "#0f1629",
        },
        // Deep navy for the sidebar / dark surfaces.
        ink: { 950: "#070c18", 900: "#0b1222", 800: "#111a30", 700: "#1a2542", 600: "#26345a" },
        surface: { DEFAULT: "#ffffff", subtle: "#f5f6fa", muted: "#eceef4", border: "#e2e5ee" },
        // Semantic status colours (info intentionally reuses the brand blue).
        status: {
          success: "#0f7b57", "success-soft": "#ddf4ea",
          warning: "#a86412", "warning-soft": "#fcf0d6",
          danger: "#c8323f", "danger-soft": "#fde5e8",
          info: "#2559c9", "info-soft": "#dde7ff",
          neutral: "#687189",
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
