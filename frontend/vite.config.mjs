import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { resolveStockExpertApiPort } from "./config/local-api.mjs";

const apiPort = resolveStockExpertApiPort();

export default defineConfig({
  optimizeDeps: {
    include: ["react", "react-dom/client"],
  },
  server: {
    host: "0.0.0.0",
    allowedHosts: ["terminal.local"],
    proxy: {
      "/api": `http://127.0.0.1:${apiPort}`,
    },
    warmup: {
      clientFiles: ["./src/main.tsx"],
    },
  },
  plugins: [react()],
});
