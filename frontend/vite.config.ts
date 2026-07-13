import react from "@vitejs/plugin-react";
import path from "node:path";
import { defineConfig } from "vite";

// Dev server proxies /api to the FastAPI backend to avoid CORS during local dev.
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { "@": path.resolve(__dirname, "./src") },
  },
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
});
