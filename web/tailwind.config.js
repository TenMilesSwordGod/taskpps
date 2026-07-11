/** @type {import('tailwindcss').Config} */

export default {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    container: {
      center: true,
    },
    extend: {
      colors: {
        column: {
          bg: "#F6F6F8",
          soft: "#FFFFFF",
          ink: "#121620",
          "ink-soft": "#7C7F88",
          accent: "#7EADFF",
          line: "#E3E4E8",
        },
      },
      borderRadius: {
        colsm: "3px",
        colmd: "8px",
        collg: "12px",
      },
      fontFamily: {
        sans: [
          "Inter",
          "-apple-system",
          "BlinkMacSystemFont",
          "Segoe UI",
          "Noto Sans",
          "Helvetica",
          "Arial",
          "sans-serif",
        ],
        mono: [
          "JetBrains Mono",
          "SF Mono",
          "Monaco",
          "Consolas",
          "Liberation Mono",
          "monospace",
        ],
      },
      boxShadow: {
        col: "rgba(1, 24, 33, 0.05) 0px 0px 0px 1px",
        "col-hover": "rgba(17, 26, 74, 0.1) 0px 1px 3px 0px",
      },
      transitionTimingFunction: {
        col: "cubic-bezier(0.76, 0, 0.24, 1)",
      },
      transitionDuration: {
        "col-micro": "220ms",
        "col-small": "400ms",
        "col-medium": "800ms",
      },
    },
  },
  plugins: [require("@tailwindcss/typography")],
};