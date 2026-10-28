import { defineConfig, devices } from "@playwright/test";

const real = process.env.DASHBOARD_TEST_MODE === "real";
const external = process.env.DASHBOARD_EXTERNAL_URL || undefined;
const local = "http://127.0.0.1:3100";
const fixture = "http://127.0.0.1:3101";

export default defineConfig({
  testDir: "./tests",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 30_000,
  expect: { timeout: 10_000 },
  reporter: [["list"]],
  use: { baseURL: external ?? local, trace: "retain-on-failure", screenshot: "only-on-failure" },
  projects: [
    { name: "fixtures", testMatch: "dashboard.spec.ts", use: { ...devices["Desktop Chrome"] } },
    { name: "real-api", testMatch: "real-api.spec.ts", use: { ...devices["Desktop Chrome"] } },
  ],
  webServer: external ? undefined : [
    ...(!real ? [{ command: "node tests/fixtures/api-server.mjs", url: fixture, reuseExistingServer: false }] : []),
    {
      command: "npm run start", url: local, reuseExistingServer: false, timeout: 60_000,
      env: { HOSTNAME: "127.0.0.1", PORT: "3100", API_BASE_URL: real
        ? (process.env.DASHBOARD_API_URL ?? "http://127.0.0.1:8000") : fixture },
    },
  ],
});
