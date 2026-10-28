import { defineConfig } from "@playwright/test";

const baseURL = "http://127.0.0.1:3100";
const useExternalServer = process.env.E2E_EXTERNAL_SERVER === "1";
const chromiumExecutablePath = process.env.E2E_CHROMIUM_EXECUTABLE_PATH;

export const frontendWebServer = {
  command: "pnpm dev --hostname 127.0.0.1 --port 3100",
  url: baseURL,
  reuseExistingServer: false,
  timeout: 120_000,
  env: { API_PROXY_URL: "http://127.0.0.1:8100" },
};

export default defineConfig({
  testDir: "./e2e",
  outputDir: ".runtime/frontend-qa/test-results",
  forbidOnly: Boolean(process.env.CI),
  retries: 0,
  workers: 1,
  reporter: [
    ["list"],
    [
      "html",
      { outputFolder: ".runtime/frontend-qa/html-report", open: "never" },
    ],
  ],
  use: {
    baseURL,
    browserName: "chromium",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    ...(chromiumExecutablePath
      ? { launchOptions: { executablePath: chromiumExecutablePath } }
      : {}),
  },
  projects: [
    {
      name: "desktop",
      testMatch: "**/*.mock.spec.ts",
      use: { viewport: { width: 1440, height: 900 } },
    },
    {
      name: "tablet",
      testMatch: "**/*.mock.spec.ts",
      use: { viewport: { width: 768, height: 1024 } },
    },
    {
      name: "mobile",
      testMatch: "**/*.mock.spec.ts",
      use: { viewport: { width: 390, height: 844 } },
    },
  ],
  webServer: useExternalServer ? undefined : frontendWebServer,
});
