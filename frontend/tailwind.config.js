/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // Premium minimal black theme: deep near-black canvas, translucent
        // hairline borders, and exactly one accent color reserved for brand
        // moments (primary actions, active states, links, data highlights).
        // Risk severity keeps its own dedicated palette so the two never compete.
        background: "#050505",
        surface: {
          DEFAULT: "#0a0a0a",
          hover: "#141414",
          card: "#0d0d0d",
        },
        border: {
          DEFAULT: "rgba(255,255,255,0.08)",
          light: "rgba(255,255,255,0.16)",
        },
        ink: {
          50: "#fafafa",
          200: "#d4d4d4",
          400: "#8a8a8a",
          500: "#6b6b6b",
          700: "#3a3a3a",
        },
        accent: {
          DEFAULT: "#4f6bff",
          hover: "#6f89ff",
          text: "#8fa2ff",
          muted: "rgba(79,107,255,0.12)",
          border: "rgba(79,107,255,0.35)",
        },
        tier: {
          low: "#22c55e",
          medium: "#eab308",
          high: "#f97316",
          critical: "#ef4444",
        },
      },
      fontFamily: {
        sans: ['Inter', '-apple-system', 'sans-serif'],
        mono: ['JetBrains Mono', 'monospace'],
      },
      borderRadius: {
        'xl': '10px',
        '2xl': '16px',
      },
      boxShadow: {
        subtle: '0 1px 2px 0 rgba(0,0,0,0.35)',
        panel: '0 12px 32px -12px rgba(0,0,0,0.55)',
        accent: '0 8px 20px -6px rgba(79,107,255,0.35)',
      },
      keyframes: {
        fadeUp: {
          '0%': { opacity: '0', transform: 'translateY(6px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        fadeIn: {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
      },
      animation: {
        'fade-up': 'fadeUp 0.45s cubic-bezier(0.16, 1, 0.3, 1) both',
        'fade-in': 'fadeIn 0.35s ease-out both',
      },
    },
  },
  plugins: [],
}
