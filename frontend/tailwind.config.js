/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // Modern minimal black theme: true-black canvas, near-black surfaces,
        // hairline borders. Color is reserved for risk severity only — all
        // UI chrome (buttons, chips, focus rings) is monochrome.
        background: "#000000",
        surface: {
          DEFAULT: "#0a0a0a",
          hover: "#121212",
          card: "#0d0d0d",
        },
        border: {
          DEFAULT: "#1f1f1f",
          light: "#2e2e2e",
        },
        ink: {
          50: "#fafafa",
          200: "#d4d4d4",
          400: "#8a8a8a",
          500: "#6b6b6b",
          700: "#3a3a3a",
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
        '2xl': '14px',
      }
    },
  },
  plugins: [],
}
