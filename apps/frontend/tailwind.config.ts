/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{vue,js,ts,jsx,tsx}",
  ],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        "primary": "#003aa2",
        "primary-container": "#004fd5",
        "on-primary": "#ffffff",
        "on-primary-container": "#c6d2ff",
        "secondary": "#5e5e5e",
        "secondary-container": "#e4e2e2",
        "on-secondary": "#ffffff",
        "on-secondary-container": "#646464",
        "tertiary": "#004a55",
        "tertiary-container": "#006472",
        "on-tertiary": "#ffffff",
        "on-tertiary-container": "#54e4fe",
        "surface": "#f7fafe",
        "surface-bright": "#f7fafe",
        "surface-container-lowest": "#ffffff",
        "surface-container-low": "#f1f4f8",
        "surface-container": "#ebeef2",
        "surface-container-high": "#e5e8ec",
        "surface-container-highest": "#e0e3e7",
        "on-surface": "#181c1f",
        "on-surface-variant": "#434654",
        "outline": "#737685",
        "outline-variant": "#c3c6d6",
        "error": "#ba1a1a",
        "error-container": "#ffdad6",
        "on-error": "#ffffff",
        "on-error-container": "#93000a",
        "background": "#f7fafe",
      },
      borderRadius: {
        "DEFAULT": "0.125rem",
        "lg": "0.25rem",
        "xl": "0.5rem",
        "full": "0.75rem"
      },
      fontFamily: {
        "headline": ["Manrope", "sans-serif"],
        "body": ["Inter", "sans-serif"],
        "label": ["Inter", "sans-serif"]
      }
    },
  },
  plugins: [],
}
