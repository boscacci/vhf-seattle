#!/usr/bin/env node
import { readFile } from "node:fs/promises";
import { chromium, firefox, webkit } from "playwright";

const playwrightPackage = JSON.parse(
  await readFile(new URL("../node_modules/playwright/package.json", import.meta.url), "utf-8"),
);
const browserTypes = { chromium, firefox, webkit };
const checks = [];
let failed = false;

for (const [name, browserType] of Object.entries(browserTypes)) {
  const check = {
    name,
    executablePath: browserType.executablePath(),
    launch: "pending",
  };
  let browser;
  try {
    browser = await browserType.launch({ headless: true });
    const page = await browser.newPage();
    await page.goto("about:blank");
    check.userAgent = await page.evaluate(() => navigator.userAgent);
    check.launch = "ok";
  } catch (error) {
    failed = true;
    check.launch = "failed";
    check.error = error instanceof Error ? error.message : String(error);
  } finally {
    if (browser) {
      await browser.close();
    }
  }
  checks.push(check);
}

console.log(
  JSON.stringify(
    {
      playwrightVersion: playwrightPackage.version,
      browsers: checks,
      installCommand: "npm run browser:install",
    },
    null,
    2,
  ),
);

if (failed) {
  process.exitCode = 1;
}
