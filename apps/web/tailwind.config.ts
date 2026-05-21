import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Override if you want a custom palette
      },
    },
  },
  plugins: [],
};

export default config;
