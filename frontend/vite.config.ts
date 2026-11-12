import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Dev: UI on :5173, API proxied to the local Thrones backend on :8765.
// Production: `npm run build` emits dist/, which the backend serves itself.
export default defineConfig({
  plugins: [react()],
  cacheDir: "../.cache/vite",
  server: {
    host: "127.0.0.1",
    port: 5173,
    proxy: { "/api": { target: "http://127.0.0.1:8765", changeOrigin: false } },
  },
  build: {
    outDir: "dist",
    chunkSizeWarningLimit: 1200,
  },
});
