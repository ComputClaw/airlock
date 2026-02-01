import { defineConfig } from "vite";
import { svelte } from "@sveltejs/vite-plugin-svelte";

export default defineConfig({
  plugins: [svelte()],
  server: {
    port: 5173,
    proxy: {
      "/api": "http://localhost:9090",
      "/health": "http://localhost:9090",
      "/execute": "http://localhost:9090",
      "/executions": "http://localhost:9090",
      "/skill.md": "http://localhost:9090",
    },
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
  },
});
