/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        brand: {
          50: "#eef4ff",
          100: "#dbe6ff",
          200: "#bcd0ff",
          300: "#8eb0ff",
          400: "#5a86fa",
          500: "#2f6fed",
          600: "#2557c7",
          700: "#1d449e",
          800: "#1b3c82",
          900: "#1a366c",
        },
        surface: { DEFAULT: "#ffffff", subtle: "#f6f7f9", muted: "#eef0f3", border: "#e4e7ec" },
        status: {
          success: "#15803d",
          "success-soft": "#dcfce7",
          warning: "#b45309",
          "warning-soft": "#fef3c7",
          danger: "#dc2626",
          "danger-soft": "#fee2e2",
          info: "#2563eb",
          "info-soft": "#dbeafe",
          neutral: "#6b7280",
        },
      },
      borderRadius: { sm: "6px", md: "8px", lg: "12px", xl: "16px" },
      fontFamily: {
        sans: ['"Inter"', '"Inter Fallback"', "system-ui", "-apple-system", "Segoe UI", "Roboto", "sans-serif"],
      },
      boxShadow: {
        sm: "0 1px 2px 0 rgba(16, 24, 40, 0.05)",
        card: "0 1px 3px rgba(16, 24, 40, 0.08), 0 1px 2px -1px rgba(16, 24, 40, 0.04)",
        md: "0 4px 12px -2px rgba(16, 24, 40, 0.10), 0 2px 6px -2px rgba(16, 24, 40, 0.06)",
        lg: "0 12px 32px -8px rgba(16, 24, 40, 0.16)",
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
