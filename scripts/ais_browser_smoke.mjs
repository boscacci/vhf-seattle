#!/usr/bin/env node
import { mkdir } from "node:fs/promises";
import { dirname, extname } from "node:path";
import { chromium } from "playwright";

const baseUrl = normalizeBaseUrl(
  process.env.TALKINGBOATS_AIS_SMOKE_BASE_URL || "https://seattleboatradio.com",
);
const timeoutMs = envNumber("TALKINGBOATS_AIS_SMOKE_TIMEOUT_MS", 20000);
const screenshotPath =
  process.env.TALKINGBOATS_AIS_SMOKE_SCREENSHOT || "outputs/ais-smoke-failure.png";
const browser = await chromium.launch({ headless: true });
const profiles = [];

try {
  profiles.push(
    await smokeProfile(browser, "desktop", {
      viewport: { width: 1440, height: 1000 },
    }),
  );
  profiles.push(
    await smokeProfile(browser, "mobile", {
      viewport: { width: 390, height: 844 },
      isMobile: true,
      hasTouch: true,
    }),
  );
} finally {
  await browser.close();
}

const failures = profiles.filter((profile) => profile.status !== "ok");
const result = {
  status: failures.length ? "failed" : "ok",
  baseUrl,
  vesselCount: Math.min(...profiles.map((profile) => profile.vesselCount || 0)),
  mapCanvasCount: Math.min(...profiles.map((profile) => profile.mapCanvasCount || 0)),
  profiles,
};
if (failures.length) {
  result.failures = failures.map((profile) => `${profile.name}: ${profile.failure}`);
  process.exitCode = 1;
}
console.log(JSON.stringify(result, null, 2));

async function smokeProfile(browserInstance, name, contextOptions) {
  const page = await browserInstance.newPage(contextOptions);
  const profile = {
    name,
    status: "ok",
    vesselCount: 0,
    mapCanvasCount: 0,
    frameTitle: "",
    mapStatus: "",
    errors: [],
  };
  page.on("pageerror", (error) => profile.errors.push(sanitize(String(error))));
  page.on("console", (message) => {
    if (message.type() === "error") {
      profile.errors.push(`console: ${sanitize(message.text())}`);
    }
  });
  page.on("requestfailed", (request) => {
    if (request.url().includes("/ais-catcher/")) {
      profile.errors.push(
        `request failed: ${sanitizeUrl(request.url())} ${request.failure()?.errorText || "unknown"}`,
      );
    }
  });

  try {
    await page.goto(`${baseUrl}/ais/?_ais_smoke=${name}-${Date.now()}`, {
      waitUntil: "domcontentloaded",
      timeout: timeoutMs,
    });
    const frameLocator = page.frameLocator("#ais-catcher-frame");
    await frameLocator.locator("body").waitFor({ state: "visible", timeout: timeoutMs });
    await page.waitForFunction(
      () => {
        const iframe = document.querySelector("#ais-catcher-frame");
        const frameDocument = iframe?.contentDocument;
        const match = frameDocument?.title.match(/^\((\d+)\)/);
        const vesselCount = Number(match?.[1] || 0);
        return vesselCount > 0 && (frameDocument?.querySelectorAll("canvas").length || 0) > 0;
      },
      null,
      { timeout: timeoutMs },
    );
    const frameState = await frameLocator.locator("body").evaluate(() => {
      const match = document.title.match(/^\((\d+)\)/);
      return {
        frameTitle: document.title,
        vesselCount: Number(match?.[1] || 0),
        mapCanvasCount: document.querySelectorAll("canvas").length,
      };
    });
    const parentState = await page.locator("#ais-catcher-frame").evaluate((iframe) => ({
      frameHidden: iframe.hidden,
      mapStatus: document.querySelector("#map-status")?.textContent?.trim() || "",
    }));
    Object.assign(profile, frameState, parentState);
    if (
      profile.vesselCount < 1 ||
      profile.mapCanvasCount < 1 ||
      profile.frameHidden ||
      !profile.mapStatus.includes("Showing AIS-catcher live map")
    ) {
      throw new Error("AIS iframe did not render live vessel content");
    }
    if (profile.errors.length) {
      throw new Error(`AIS browser errors: ${profile.errors.join(" | ")}`);
    }
  } catch (error) {
    profile.status = "failed";
    profile.failure = sanitize(error instanceof Error ? error.message : String(error));
    const profileScreenshot = screenshotForProfile(screenshotPath, name);
    await mkdir(dirname(profileScreenshot), { recursive: true });
    await page.screenshot({ path: profileScreenshot, fullPage: true }).catch(() => {});
    profile.screenshotPath = profileScreenshot;
  } finally {
    await page.close();
  }
  return profile;
}

function screenshotForProfile(path, profileName) {
  const extension = extname(path);
  return extension
    ? `${path.slice(0, -extension.length)}-${profileName}${extension}`
    : `${path}-${profileName}`;
}

function normalizeBaseUrl(value) {
  return value.replace(/\/+$/, "");
}

function envNumber(name, fallback) {
  const value = Number(process.env[name]);
  return Number.isFinite(value) && value > 0 ? value : fallback;
}

function sanitizeUrl(value) {
  try {
    const url = new URL(value);
    return `${url.origin}${url.pathname}`;
  } catch {
    return "[url]";
  }
}

function sanitize(value) {
  return value.replace(/https:\/\/[^'"\s)]+/g, sanitizeUrl).slice(0, 400);
}
