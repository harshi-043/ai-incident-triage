/// <reference types="vitest/config" />
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig, loadEnv } from "vite";

export default defineConfig(({ mode }) => {
  // During development the browser talks to Vite (port 5173) and Vite forwards /api calls to the backend,
  // so the frontend does not need to know the backend address. Override with VITE_DEV_API_TARGET if needed.
  const env = loadEnv(mode, ".", "");
  const backend = env.VITE_DEV_API_TARGET || "http://127.0.0.1:8001";

  return {
    plugins: [react(), tailwindcss()],
    server: { port: 5173, proxy: { "/api": { target: backend, changeOrigin: true } } },
    test: {
      environment: "jsdom",
      globals: true,
      setupFiles: ["./src/test/setup.ts"],
      css: false,
    },
  };
});
