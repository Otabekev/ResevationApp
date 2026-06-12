import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { VitePWA } from "vite-plugin-pwa";

export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      registerType: "autoUpdate",
      // Files copied verbatim into dist (referenced from index.html). The iOS
      // home-screen icon points at /icons/icon-192.png — see the apple-touch-icon
      // link tag — so we don't ship a separate apple-touch-icon.png.
      includeAssets: ["favicon.ico", "icons/icon-192.png"],
      manifest: {
        name: "Qulay Navbat — Online Booking",
        short_name: "Qulay Navbat",
        description: "Online appointment booking for Uzbekistan businesses",
        theme_color: "#0C6E56",
        background_color: "#F7F5F1",
        display: "standalone",
        start_url: "/",
        scope: "/",
        orientation: "portrait",
        lang: "uz",
        dir: "ltr",
        categories: ["business", "productivity"],
        icons: [
          // SVG declares maskable safely (vector — no cropping risk).
          { src: "/icons/icon.svg", sizes: "any", type: "image/svg+xml", purpose: "any maskable" },
          // PNGs ship as "any" only — the source art isn't safe-area-padded,
          // so declaring maskable would crop the logo on Android launchers.
          { src: "/icons/icon-192.png", sizes: "192x192", type: "image/png", purpose: "any" },
          { src: "/icons/icon-512.png", sizes: "512x512", type: "image/png", purpose: "any" },
        ],
      },
    }),
  ],
  server: {
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
});
