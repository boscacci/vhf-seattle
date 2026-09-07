#!/usr/bin/env node
import { chromium } from "playwright";

const baseUrl = String(
  process.env.TALKINGBOATS_PERFORMANCE_SMOKE_BASE_URL || "https://seattleboatradio.com",
).replace(/\/+$/, "");
const timeoutMs = 20_000;
const profiles = [
  { name: "mobile", viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true },
  { name: "desktop", viewport: { width: 1280, height: 900 } },
];

const browser = await chromium.launch({ headless: true });
const checks = [];
try {
  for (const profile of profiles) {
    const context = await browser.newContext(profile);
    try {
      const page = await context.newPage();
      const errors = [];
      page.on("pageerror", (error) => errors.push(error.message));
      await page.goto(`${baseUrl}/performance/?_thermal_smoke=${profile.name}-${Date.now()}`, {
        waitUntil: "domcontentloaded",
        timeout: timeoutMs,
      });
      await page.locator(".thermal-balance-card").first().waitFor({
        state: "visible",
        timeout: timeoutMs,
      });
      const state = await page.evaluate(() => {
        const firstHost = document.querySelector(".performance-host");
        const card = firstHost?.querySelector(".thermal-balance-card");
        return {
          host: firstHost?.querySelector("h3")?.textContent?.trim() || "",
          text: card?.textContent || "",
          sensors: [...(card?.querySelectorAll(".thermal-sensor-row") || [])].map(
            (row) => row.textContent || "",
          ),
          viewportWidth: document.documentElement.clientWidth,
          scrollWidth: document.documentElement.scrollWidth,
        };
      });
      if (state.host !== "Ubuntu Micro-Computer") {
        throw new Error(`unexpected first telemetry host: ${state.host}`);
      }
      if (!state.text.includes("Thermal balance") || !state.text.includes("worst sensor controls status")) {
        throw new Error(`combined thermal explanation is missing: ${state.text}`);
      }
      if (state.sensors.length < 2) {
        throw new Error(`combined thermal view exposed only ${state.sensors.length} sensor group(s)`);
      }
      if (state.scrollWidth > state.viewportWidth) {
        throw new Error(`page overflows horizontally: ${state.scrollWidth} > ${state.viewportWidth}`);
      }
      if (errors.length) {
        throw new Error(`browser errors: ${errors.join("; ")}`);
      }
      checks.push({ name: profile.name, status: "ok", ...state });
    } finally {
      await context.close();
    }
  }
} finally {
  await browser.close();
}

console.log(JSON.stringify({ status: "ok", baseUrl, checks }, null, 2));
