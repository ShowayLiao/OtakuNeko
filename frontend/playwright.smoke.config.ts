import { defineConfig } from "@playwright/test";
import baseConfig, { frontendWebServer } from "./playwright.config";

export default defineConfig({
  ...baseConfig,
  outputDir: ".runtime/frontend-qa/smoke-test-results",
  reporter: [
    ["list"],
    [
      "html",
      { outputFolder: ".runtime/frontend-qa/smoke-html-report", open: "never" },
    ],
  ],
  projects: [
    {
      name: "smoke",
      testMatch: "**/*.smoke.spec.ts",
      use: { viewport: { width: 1440, height: 900 } },
    },
  ],
  webServer: [
    {
      command: "node e2e/start-backend.mjs",
      url: "http://127.0.0.1:8100/health",
      reuseExistingServer: false,
      timeout: 120_000,
    },
    frontendWebServer,
  ],
});
