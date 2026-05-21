/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        "border-subtle": "rgba(255,255,255,0.1)",
        "surface-elevated": "#242424",
        primary: "#6fd8c9",
        "primary-container": "#2fa194",
        "on-primary": "#003732",
        surface: "#131313",
        background: "#131313",
        "on-background": "#e5e2e1",
        "on-surface": "#e5e2e1",
        "on-surface-variant": "#bcc9c6",
        "surface-container": "#201f1f",
        "surface-container-lowest": "#0e0e0e",
        "surface-container-low": "#1c1b1b",
        "surface-container-high": "#2a2a2a",
        "surface-variant": "#353535",
        "surface-bright": "#393939",
        "text-muted": "#A0A0A0",
        error: "#ffb4ab",
        tertiary: "#ffb59e",
        "tertiary-container": "#d2795c",
        secondary: "#c6c6c7",
        outline: "#879390",
        "outline-variant": "#3d4947"
      },
      fontFamily: {
        "display-lg": ["Geist", "sans-serif"],
        "headline-lg": ["Geist", "sans-serif"],
        "headline-lg-mobile": ["Geist", "sans-serif"],
        "body-md": ["Inter", "sans-serif"],
        "code-sm": ["JetBrains Mono", "monospace"],
        "label-xs": ["JetBrains Mono", "monospace"]
      }
    },
  },
  plugins: [],
}
