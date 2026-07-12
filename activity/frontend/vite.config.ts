import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Discord serves the Activity through its proxy at
// https://<CLIENT_ID>.discordsays.com and rewrites `/.proxy/*` to your
// backend. During local dev we proxy `/.proxy/api` and `/api` to the local
// FastAPI so `fetch("/.proxy/api/...")` works both in the tunnel and locally.
const API_TARGET = process.env.VITE_API_TARGET ?? "http://localhost:8080";

export default defineConfig({
  plugins: [react()],
  server: {
    // Discord loads the app over the tunnel; allow the tunnel host and let
    // Vite bind on all interfaces so cloudflared can reach it.
    host: true,
    port: 5173,
    allowedHosts: true,
    proxy: {
      "/.proxy/api": {
        target: API_TARGET,
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/\.proxy/, ""),
      },
      "/api": {
        target: API_TARGET,
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: "dist",
  },
});
