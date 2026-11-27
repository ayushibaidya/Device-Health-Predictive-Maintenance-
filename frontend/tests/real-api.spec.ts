import { expect, test } from "@playwright/test";

test("real simulator pipeline: fleet -> select device -> device and history", async ({ page, request }) => {
  const api = process.env.DASHBOARD_API_URL ?? "http://127.0.0.1:8000";
  const response = await request.get(`${api}/api/v1/devices`);
  expect(response.ok()).toBeTruthy();
  const devices = await response.json();
  expect(devices.items.length, "Seed the backend with scripts/demo-api.sh first").toBeGreaterThan(0);
  const deviceId: string = devices.items[0].event.device_id;
  const detail = await (await request.get(`${api}/api/v1/devices/${encodeURIComponent(deviceId)}`)).json();
  const browserRequests: string[] = [];
  page.on("request", req => browserRequests.push(req.url()));
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Fleet overview", exact: true })).toBeVisible();
  await expect(page.getByRole("columnheader", { name: "Errors", exact: true })).toBeVisible();
  const row = page.getByRole("row").filter({ has: page.getByRole("link", { name: `Inspect ${deviceId}` }) });
  await expect(row.getByRole("cell").nth(5)).toHaveText(new Intl.NumberFormat("en-US").format(detail.event.error_count));
  await page.getByRole("link", { name: `Inspect ${deviceId}` }).click();
  await expect(page.getByRole("heading", { name: deviceId, level: 1, exact: true })).toBeVisible();
  await expect(page.getByText(detail.event.run_id, { exact: true })).toBeVisible();
  await expect(page.getByRole("region", { name: "Latest telemetry" })).toBeVisible();
  await expect(page.getByRole("table", { name: "Telemetry readings" })).toBeVisible();
  await expect(page.locator("[data-chart] svg[role='application']")).toHaveCount(4);
  expect(browserRequests.some(url => url.startsWith(api))).toBe(false);
});
