/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        arena: {
          yellow: "#FFD700",
          yellowh: "#FFE44D",
          bg: "#000000",
          panel: "#0c0c0c",
          card: "#101010",
          hit: "#38D66B",
          miss: "#FF4B44",
          missText: "#FF6B63",
        },
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "monospace"],
      },
    },
  },
  plugins: [],
};
