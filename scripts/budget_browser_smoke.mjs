import assert from "node:assert/strict";
import fs from "node:fs/promises";
import { createRequire } from "node:module";
import path from "node:path";

const { chromium } = createRequire(path.join(
  process.env.TALKINGBOATS_BROWSER_DEPENDENCY_ROOT || process.cwd(), "package.json",
))("playwright");
const baseUrl = process.env.TALKINGBOATS_BUDGET_SMOKE_BASE_URL || "https://dev.seattleboatradio.com";
const browser = await chromium.launch({ headless: true });
const checks = [];
const failureDir = process.env.TALKINGBOATS_BUDGET_SMOKE_OUTPUT_DIR || "outputs/budget-smoke";
try {
  for (const viewport of [{ width: 390, height: 844 }, { width: 1280, height: 900 }]) {
    const context = await browser.newContext({ viewport });
    await context.tracing.start({ screenshots: true, snapshots: true });
    const page = await context.newPage();
    const errors = [];
    page.on("pageerror", error => errors.push(error.message));
    try {
      const response = await page.request.get(`${baseUrl}/operations.json`);
      assert.equal(response.status(), 200);
      const snapshot = await response.json();
      assert.equal(snapshot.budget.scope, "project");
      assert.equal(snapshot.budget.month, new Date().toISOString().slice(0, 7) + "-01");
      const { monthToDateUsd: spent, limitUsd: limit, usedPercent: used } = snapshot.budget;
      assert(Number.isFinite(spent) && spent >= 0);
      assert.equal(limit, 35);
      assert.equal(used, Math.round(spent / limit * 10000) / 100);
      await page.goto(`${baseUrl}/performance/`, { waitUntil: "domcontentloaded" });
      const card = page.locator(".cloud-operations-panel .system-kpi-card")
        .filter({ hasText: "Monthly AWS spend" });
      await card.waitFor({ state: "visible", timeout: 20000 });
      const text = await card.innerText();
      assert(text.includes(`$${spent.toFixed(2)}`), text);
      assert(text.includes(`${used.toFixed(1)}%`), text);
      assert(text.includes(`$${limit.toFixed(2)}`), text);
      assert.equal(await page.evaluate(() =>
        document.documentElement.scrollWidth > document.documentElement.clientWidth), false);
      assert.deepEqual(errors, []);
      checks.push({ viewport, scope: "project", spent, limit, used, card: text });
      await context.tracing.stop();
    } catch (error) {
      await fs.mkdir(failureDir, { recursive: true });
      await page.screenshot({ path: path.join(failureDir, `budget-${viewport.width}.png`), fullPage: true }).catch(() => {});
      await context.tracing.stop({ path: path.join(failureDir, `budget-${viewport.width}.zip`) });
      throw error;
    } finally {
      await context.close();
    }
  }
} finally {
  await browser.close();
}
console.log(JSON.stringify({ status: "ok", baseUrl, checks }, null, 2));
