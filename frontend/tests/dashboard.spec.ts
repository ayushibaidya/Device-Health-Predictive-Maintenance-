import { expect, test } from "@playwright/test";

const fixture = "http://127.0.0.1:3101";
test.beforeEach(async ({ request }) => { await request.post(`${fixture}/__test__/scenario/default`); });

test("fleet renders every API page and all four reported health counts", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Fleet overview", exact: true })).toBeVisible();
  const summary = page.getByRole("region", { name: "Fleet health summary" });
  await expect(summary).toContainText("Total devices4");
  for (const state of ["Healthy", "Warning", "Critical", "Failed"]) await expect(summary).toContainText(`${state}1`);
  await expect(page.getByRole("table").getByRole("row")).toHaveCount(5);
  await expect(page.getByRole("link", { name: "Inspect device-004" })).toBeVisible();
  await expect(page.getByText("Simulated data", { exact: true })).toBeVisible();
  await expect(page.getByRole("columnheader", { name: "Errors", exact: true })).toBeVisible();
  const rows = page.getByRole("table").getByRole("row");
  for (let index = 0; index < 4; index++) {
    await expect(rows.nth(index + 1).getByRole("cell").nth(5)).toHaveText(String(index));
  }
  await expect(page.getByText("Health states are reported by the simulator.", { exact: false })).toBeVisible();
});

test("selecting a device loads metadata, latest values, four charts and back navigation", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("link", { name: "Inspect device-001" }).click();
  await expect(page).toHaveURL(/\/devices\/device-001$/);
  await expect(page.getByRole("heading", { level: 1, name: "device-001" })).toBeVisible();
  await expect(page.getByText("1.2.0", { exact: true })).toBeVisible();
  await expect(page.getByRole("region", { name: "Latest telemetry" })).toContainText("44");
  await expect(page.locator("[data-chart] svg[role='application']")).toHaveCount(4);
  await expect(page.getByRole("table", { name: "Telemetry readings" }).getByRole("row")).toHaveCount(4);
  await page.getByRole("link", { name: "Back to fleet", exact: false }).click();
  await expect(page.getByRole("heading", { name: "Fleet overview", exact: true })).toBeVisible();
});

test("history cursors change the selected window while the header remains current", async ({ page }) => {
  await page.goto("/devices/device-001");
  await page.getByRole("link", { name: "Older readings" }).click();
  await expect(page).toHaveURL(/before=102/);
  await expect(page.getByRole("table", { name: "Telemetry readings" }).getByRole("row")).toHaveCount(2);
  await expect(page.getByRole("definition").filter({ hasText: "#104" })).toBeVisible();
  await page.getByRole("link", { name: "Latest readings" }).click();
  await expect(page).not.toHaveURL(/before=/);
  await expect(page.getByRole("table", { name: "Telemetry readings" }).getByRole("row")).toHaveCount(4);
});

test("fleet loading placeholders are visible before data arrives", async ({ page, request }) => {
  await request.post(`${fixture}/__test__/scenario/delay`);
  await page.goto("/", { waitUntil: "commit" });
  await expect(page.getByRole("status", { name: "Loading devices" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Inspect device-001" })).toBeVisible();
});

test("device navigation shows a loading state", async ({ page, request }) => {
  await page.goto("/");
  await expect(page.getByRole("link", { name: "Inspect device-001" })).toBeVisible();
  await request.post(`${fixture}/__test__/scenario/delay`);
  await page.getByRole("link", { name: "Inspect device-001" }).click();
  await expect(page.getByRole("status", { name: "Loading device details" })).toBeVisible();
  await expect(page.getByRole("heading", { level: 1, name: "device-001" })).toBeVisible();
});

test("an empty fleet has an honest empty state", async ({ page, request }) => {
  await request.post(`${fixture}/__test__/scenario/empty`);
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "No devices yet" })).toBeVisible();
  await expect(page.getByRole("table")).toHaveCount(0);
  await expect(page.getByRole("region", { name: "Fleet health summary" })).toContainText("Total devices0");
});

test("the full device row opens detail, including native new-tab behavior", async ({ page, context }) => {
  await page.goto("/");
  const row = page.getByRole("row").filter({ has: page.getByRole("link", { name: "Inspect device-004" }) });
  await expect(row.getByText("View details")).toBeVisible();
  const errorCell = row.getByRole("cell").nth(5);
  const box = await errorCell.boundingBox();
  expect(box).not.toBeNull();
  const popupPromise = context.waitForEvent("page");
  // Use coordinates so this specifically hits the row surface, not the ID link text.
  await page.mouse.click(box!.x + box!.width / 2, box!.y + box!.height / 2, { button: "middle" });
  const popup = await popupPromise;
  await expect(popup).toHaveURL(/\/devices\/device-004$/);
  await expect(popup.getByRole("heading", { name: "device-004", level: 1 })).toBeVisible();
  await popup.close();
  await page.mouse.click(box!.x + box!.width / 2, box!.y + box!.height / 2);
  await expect(page.getByRole("heading", { name: "device-004", level: 1 })).toBeVisible();
});

test("the desktop fleet footer follows the content without a forced viewport gap", async ({ page }) => {
  await page.setViewportSize({ width: 1600, height: 1200 });
  await page.goto("/");
  await expect(page.getByRole("link", { name: "Inspect device-004" })).toBeVisible();
  const note = await page.locator(".data-note").boundingBox();
  const footer = await page.getByRole("contentinfo").boundingBox();
  expect(note).not.toBeNull();
  expect(footer).not.toBeNull();
  expect(footer!.y - (note!.y + note!.height)).toBeLessThanOrEqual(48);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBe(true);
});

test("API failure offers a retry that recovers without fixture fallback", async ({ page, request }) => {
  await request.post(`${fixture}/__test__/scenario/api-error`);
  await page.goto("/");
  const error = page.getByRole("alert").filter({ has: page.getByRole("heading", { name: "Device data unavailable" }) });
  await expect(error).toBeVisible();
  await expect(page.getByRole("link", { name: "Inspect device-001" })).toHaveCount(0);
  await request.post(`${fixture}/__test__/scenario/default`);
  await error.getByRole("button", { name: "Try again" }).click();
  await expect(page.getByRole("link", { name: "Inspect device-001" })).toBeVisible();
});

test("summary failure preserves available devices", async ({ page, request }) => {
  await request.post(`${fixture}/__test__/scenario/summary-error`);
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Fleet summary unavailable" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Inspect device-004" })).toBeVisible();
});

test("device 404 is distinct from an API outage", async ({ page, request }) => {
  await page.goto("/devices/unknown-device");
  await expect(page.getByRole("heading", { name: "Device not found" })).toBeVisible();
  await page.getByRole("link", { name: "Back to fleet", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Fleet overview", exact: true })).toBeVisible();
  await request.post(`${fixture}/__test__/scenario/api-error`);
  await page.goto("/devices/device-001");
  await expect(page.getByRole("heading", { name: "Device data unavailable" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Device not found" })).toHaveCount(0);
});

test("empty history renders an empty state instead of invented charts", async ({ page, request }) => {
  await request.post(`${fixture}/__test__/scenario/history-empty`);
  await page.goto("/devices/device-001");
  await expect(page.getByRole("heading", { name: "No telemetry in this window" })).toBeVisible();
  await expect(page.locator("[data-chart]")).toHaveCount(0);
});

test("history failure preserves latest telemetry", async ({ page, request }) => {
  await request.post(`${fixture}/__test__/scenario/history-error`);
  await page.goto("/devices/device-001");
  await expect(page.getByRole("heading", { name: "Telemetry history unavailable" })).toBeVisible();
  await expect(page.getByRole("region", { name: "Latest telemetry" })).toContainText("44");
});

test("manual refresh fetches updated API data", async ({ page, request }) => {
  await page.goto("/devices/device-001");
  await expect(page.getByRole("region", { name: "Latest telemetry" })).toContainText("44");
  await request.post(`${fixture}/__test__/scenario/updated`);
  await page.getByRole("button", { name: "Refresh data" }).click();
  await expect(page.getByRole("region", { name: "Latest telemetry" })).toContainText("65");
});

test("optional null metrics are unavailable, while real zeros are shown", async ({ page }) => {
  await page.goto("/devices/device-002");
  const metrics = page.getByRole("region", { name: "Latest telemetry" });
  await expect(metrics).toContainText("Actuator loadUnavailable");
  await expect(metrics).toContainText("Position error0mm");
});

test("invalid responses and repeated cursors fail safely", async ({ page, request }) => {
  for (const scenario of ["malformed", "bad-cursor"]) {
    await request.post(`${fixture}/__test__/scenario/${scenario}`);
    await page.goto("/");
    await expect(page.getByRole("heading", { name: "Device data unavailable" })).toBeVisible();
    await expect(page.getByText("INVENTED_STATE")).toHaveCount(0);
  }
});

test("desktop, laptop and narrow layouts contain their horizontal overflow", async ({ page }) => {
  for (const width of [1440, 1024, 390]) {
    await page.setViewportSize({ width, height: 900 });
    await page.goto("/devices/device-001");
    await expect(page.locator("[data-chart] svg[role='application']")).toHaveCount(4);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBe(true);
  }
});

test("device selection and chart points are keyboard accessible", async ({ page }) => {
  await page.goto("/");
  const link = page.getByRole("link", { name: "Inspect device-001" });
  await link.focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("heading", { level: 1, name: "device-001" })).toBeVisible();
  const chart = page.locator("[data-chart='Temperature'] svg[role='application']");
  await chart.focus();
  await page.keyboard.press("ArrowRight");
  await expect(page.locator(".recharts-tooltip-wrapper").first()).toBeVisible();
});
