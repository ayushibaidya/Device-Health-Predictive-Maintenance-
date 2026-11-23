import { expect, test } from "@playwright/test";

const fixture = "http://127.0.0.1:3101";
test.beforeEach(async ({ request }) => { await request.post(`${fixture}/__test__/scenario/alerts`); });

test("fleet and device panels link to filtered history, keeping health counts", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("region", { name: "Fleet health summary" })).toContainText("Total devices4");
  const panel = page.getByRole("region", { name: "Recent open alerts" });
  await expect(panel.getByRole("article")).toHaveCount(2);
  await expect(panel.getByText("Acknowledged", { exact: true })).toBeVisible();
  await page.getByRole("link", { name: "Inspect device-002" }).click();
  await panel.getByRole("link", { name: "View all alerts" }).click();
  await expect(page).toHaveURL(/view=all&device=device-002/);
  await expect(page.getByLabel("Device", { exact: true })).toHaveValue("device-002");
  await expect(page.getByRole("heading", { name: "All alerts", exact: true })).toBeVisible();
  await expect(page.getByRole("link", { name: "Alerts", exact: true })).toHaveAttribute("aria-current", "page");
});

test("views and filters preserve device and severity through pagination", async ({ page }) => {
  await page.goto("/alerts?view=all&device=device-002&severity=WARNING");
  const results = page.getByRole("region", { name: "Alert results" });
  await expect(results.getByRole("article")).toHaveCount(2);
  await page.getByRole("link", { name: "Older alerts" }).click();
  await expect(page).toHaveURL(/view=all&device=device-002&severity=WARNING&before=4/);
  await expect(results.getByRole("article")).toHaveCount(1);
  await expect(results).toContainText("Recovered");
  await expect(results.getByRole("button", { name: "Acknowledge", exact: true })).toHaveCount(0);
  await page.getByRole("link", { name: "Newest alerts" }).click();
  await page.getByRole("link", { name: "Resolved", exact: true }).click();
  await expect(page).not.toHaveURL(/before=/);
  await expect(results.getByRole("article")).toHaveCount(1);
  await page.getByRole("combobox", { name: "Severity", exact: true }).selectOption("CRITICAL");
  await page.getByRole("button", { name: "Apply filters" }).click();
  await expect(page.getByRole("heading", { name: "No alerts in this view" })).toBeVisible();
});

test("acknowledgement shows pending, remains open and survives refresh", async ({ page }) => {
  const requests: string[] = [];
  page.on("request", request => requests.push(request.url()));
  await page.goto("/alerts");
  const episode = page.getByRole("article", { name: "WARNING alert for device-002" }).first();
  await episode.getByRole("button", { name: "Acknowledge", exact: true }).click();
  await expect(episode.getByRole("button", { name: "Acknowledging…" })).toBeDisabled();
  await expect(episode.getByText("Acknowledged", { exact: true })).toBeVisible();
  await expect(episode.getByText("Acknowledged · wall clock")).toBeVisible();
  await expect(episode.getByRole("button")).toHaveCount(0);
  await page.reload();
  await expect(episode.getByText("2026-10-29 12:03:00 UTC", { exact: true })).toBeVisible();
  expect(requests.some(url => url.startsWith(fixture))).toBe(false);
});

test("acknowledgement failure keeps the action available for retry", async ({ page, request }) => {
  await request.post(`${fixture}/__test__/scenario/alerts-ack-error`);
  await page.goto("/alerts");
  const episode = page.getByRole("article").first();
  await episode.getByRole("button", { name: "Acknowledge", exact: true }).click();
  await expect(page.getByRole("alert").filter({ hasText: "Could not acknowledge" })).toBeVisible();
  await expect(episode.getByRole("button", { name: "Acknowledge", exact: true })).toBeEnabled();
});

test("resolved acknowledgement conflict refreshes the open view", async ({ page, request }) => {
  await request.post(`${fixture}/__test__/scenario/alerts-conflict`);
  await page.goto("/alerts");
  await page.getByRole("article").first().getByRole("button", { name: "Acknowledge", exact: true }).click();
  await expect(page.getByRole("article")).toHaveCount(2);
  await expect(page.getByRole("article").first().getByText("Acknowledged", { exact: true })).toBeVisible();
  await expect(page.getByRole("status").filter({ hasText: "already resolved" })).toBeVisible();
  // Feedback must survive even when the last episode leaves each screen's open list.
  for (const path of ["/alerts", "/devices/device-002", "/"]) {
    await request.post(`${fixture}/__test__/scenario/alerts-conflict-single`);
    await page.goto(path);
    await page.getByRole("button", { name: "Acknowledge", exact: true }).click();
    await expect(page.getByRole("status").filter({ hasText: "already resolved" })).toBeVisible();
    await expect(page.getByRole("article")).toHaveCount(0);
  }
});

test("loading, API failure, empty and invalid filter states remain explicit", async ({ page, request }) => {
  await request.post(`${fixture}/__test__/scenario/alerts-delay`);
  await page.goto("/alerts", { waitUntil: "commit" });
  await expect(page.getByRole("status", { name: "Loading alerts" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Open alerts", exact: true })).toBeVisible();
  await request.post(`${fixture}/__test__/scenario/alerts-error`);
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Alerts unavailable" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Inspect device-001" })).toBeVisible();
  await page.goto("/alerts");
  await expect(page.getByRole("heading", { name: "Alerts unavailable" })).toBeVisible();
  await request.post(`${fixture}/__test__/scenario/default`);
  await page.getByRole("button", { name: "Try again" }).click();
  await expect(page.getByRole("heading", { name: "No alerts in this view" })).toBeVisible();
  await page.goto("/alerts?before=invalid");
  await expect(page.getByRole("heading", { name: "Invalid alert filters" })).toBeVisible();
});

test("alerts stay usable on a narrow screen and support keyboard actions", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/alerts");
  const button = page.getByRole("button", { name: "Acknowledge", exact: true }).first();
  await button.focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("article").first().getByText("Acknowledged", { exact: true })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBe(true);
  await expect(page.getByRole("link", { name: "Fleet overview", exact: true })).toBeVisible();
});
