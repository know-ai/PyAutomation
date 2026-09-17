import { test, expect } from "@playwright/test";

test("hover on tag list does not reset scroll", async ({ page }) => {
  await page.goto("/hmi/#/real-time-trends");
  await page.getByRole("button", { name: /editar panel/i }).click();
  await page.getByRole("button", { name: /tags \(\d+\)/i }).first().click();
  const list = page.locator(".multi-select-search-list");
  await list.evaluate((el) => {
    (el as HTMLElement).scrollTop = 300;
  });
  const before = await list.evaluate((el) => (el as HTMLElement).scrollTop);
  expect(before).toBeGreaterThanOrEqual(299);

  const box = await list.boundingBox();
  if (!box) throw new Error("List not visible");
  for (let i = 0; i < 20; i++) {
    await page.mouse.move(box.x + 20, box.y + 30 + i * 5);
    await page.waitForTimeout(50);
  }

  const after = await list.evaluate((el) => (el as HTMLElement).scrollTop);
  expect(Math.abs(after - before)).toBeLessThanOrEqual(1);
});

test("hover does not trigger re-render of picker", async ({ page }) => {
  await page.goto("/hmi/#/real-time-trends");
  await page.getByRole("button", { name: /editar panel/i }).click();
  await page.getByRole("button", { name: /tags \(\d+\)/i }).first().click();
  const renderCountBefore = await page.evaluate(
    () => (window as unknown as { __pickerRenderCount?: number }).__pickerRenderCount || 0
  );
  await page.mouse.move(100, 100);
  await page.mouse.move(200, 200);
  await page.waitForTimeout(1000);
  const renderCountAfter = await page.evaluate(
    () => (window as unknown as { __pickerRenderCount?: number }).__pickerRenderCount || 0
  );
  expect(renderCountAfter - renderCountBefore).toBeLessThanOrEqual(1);
});
