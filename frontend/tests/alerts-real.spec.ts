import { expect, test } from "@playwright/test";

test("real C++ pipeline: investigate failure, acknowledge, reload and reject resolved acknowledgement", async ({ page, request }) => {
  const api = process.env.DASHBOARD_API_URL ?? "http://127.0.0.1:8000";
  const open = await (await request.get(`${api}/api/v1/alerts?device_id=device-002&status=ACTIVE&severity=FAILURE`)).json();
  expect(open.items, "Seed the 1,200-step alerts scenario first").toHaveLength(1);
  const alert = open.items[0];
  const requests: string[] = [];
  page.on("request", req => requests.push(req.url()));
  await page.goto("/");
  const panel = page.getByRole("region", { name: "Recent open alerts" });
  await expect(panel).toContainText("Failure");
  await panel.getByRole("link", { name: "device-002", exact: true }).click();
  await expect(page.getByRole("heading", { name: "device-002", level: 1 })).toBeVisible();
  await page.getByRole("link", { name: "View all alerts" }).click();
  await expect(page).toHaveURL(/device=device-002/);
  const failure = page.getByRole("article", { name: "FAILURE alert for device-002" }).first();
  await failure.getByRole("button", { name: "Acknowledge", exact: true }).click();
  await expect(failure.getByText("Acknowledged", { exact: true })).toBeVisible();
  await page.reload();
  await expect(failure.getByText("Acknowledged · wall clock")).toBeVisible();
  const persisted = await (await request.get(`${api}/api/v1/alerts/${alert.alert_id}`)).json();
  const repeat = await (await request.post(`${api}/api/v1/alerts/${alert.alert_id}/acknowledge`)).json();
  expect(repeat).toEqual(persisted);
  const resolved = await (await request.get(`${api}/api/v1/alerts?device_id=device-003&status=RESOLVED`)).json();
  expect(resolved.items.some((item: { resolution_reason: string }) => item.resolution_reason === "recovered")).toBe(true);
  expect((await request.post(`${api}/api/v1/alerts/${resolved.items[0].alert_id}/acknowledge`)).status()).toBe(409);
  expect(requests.some(url => url.startsWith(api))).toBe(false);
});
