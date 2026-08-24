#!/usr/bin/env node
import { performance } from "node:perf_hooks";
import { chromium } from "playwright";

const baseUrl = normalizeBaseUrl(
  process.env.TALKINGBOATS_SLO_BASE_URL || "https://dev.seattleboatradio.com",
);
const sampleCount = envNumber("TALKINGBOATS_SLO_API_SAMPLES", 5);
const requestTimeoutMs = envNumber("TALKINGBOATS_SLO_REQUEST_TIMEOUT_MS", 8000);
const budgets = {
  recentApiP95Ms: envNumber("TALKINGBOATS_SLO_RECENT_API_P95_MS", 1500),
  loadMoreApiP95Ms: envNumber("TALKINGBOATS_SLO_LOAD_MORE_API_P95_MS", 1500),
  oldestApiP95Ms: envNumber("TALKINGBOATS_SLO_OLDEST_API_P95_MS", 1500),
  mobileClipReadyMs: envNumber("TALKINGBOATS_SLO_MOBILE_CLIP_READY_MS", 2000),
  loadMoreReadyMs: envNumber("TALKINGBOATS_SLO_LOAD_MORE_READY_MS", 3000),
  oldestBatchReadyMs: envNumber("TALKINGBOATS_SLO_OLDEST_BATCH_READY_MS", 2000),
  clipAllButTrafficReadyMs: envNumber(
    "TALKINGBOATS_SLO_CLIP_ALL_BUT_TRAFFIC_READY_MS",
    2000,
  ),
  allButTrafficSelectorReadyMs: envNumber(
    "TALKINGBOATS_SLO_ALL_BUT_TRAFFIC_SELECTOR_READY_MS",
    2000,
  ),
  allButTrafficQueueReadyMs: envNumber(
    "TALKINGBOATS_SLO_ALL_BUT_TRAFFIC_QUEUE_READY_MS",
    2000,
  ),
};

const recentFastPath =
  "/api/clips/recent?limit=24&include_playback_url=false&verify_playback_exists=false&include_counts=false";
const allButTrafficFastPath = `${recentFastPath}&exclude_channels=14`;
const oldestFastPath = `${recentFastPath}&sort=oldest`;

const result = {
  status: "ok",
  baseUrl,
  budgets,
  api: {
    everything: await sampleRecentEndpoint(recentFastPath),
    allButTraffic: await sampleRecentEndpoint(allButTrafficFastPath),
    secondBatch: await sampleCursorEndpoint(recentFastPath),
    oldest: await sampleRecentEndpoint(oldestFastPath),
  },
  browser: await measureMobileLiveInteraction(),
};
const failures = [
  ...assertP95("api.everything", result.api.everything, budgets.recentApiP95Ms),
  ...assertP95("api.allButTraffic", result.api.allButTraffic, budgets.recentApiP95Ms),
  ...assertP95("api.secondBatch", result.api.secondBatch, budgets.loadMoreApiP95Ms),
  ...assertP95("api.oldest", result.api.oldest, budgets.oldestApiP95Ms),
  ...assertMax(
    "browser.mobileClipReadyMs",
    result.browser.mobileClipReadyMs,
    budgets.mobileClipReadyMs,
  ),
  ...assertMax(
    "browser.loadMoreReadyMs",
    result.browser.loadMoreReadyMs,
    budgets.loadMoreReadyMs,
  ),
  ...assertMax(
    "browser.oldestBatchReadyMs",
    result.browser.oldestBatchReadyMs,
    budgets.oldestBatchReadyMs,
  ),
  ...assertMax(
    "browser.clipAllButTrafficReadyMs",
    result.browser.clipAllButTrafficReadyMs,
    budgets.clipAllButTrafficReadyMs,
  ),
  ...assertMax(
    "browser.allButTrafficSelectorReadyMs",
    result.browser.allButTrafficSelectorReadyMs,
    budgets.allButTrafficSelectorReadyMs,
  ),
  ...assertMax(
    "browser.allButTrafficQueueReadyMs",
    result.browser.allButTrafficQueueReadyMs,
    budgets.allButTrafficQueueReadyMs,
  ),
];
if (result.browser.errors.length) {
  failures.push(`browser console/page errors: ${result.browser.errors.join(" | ")}`);
}
if (failures.length) {
  result.status = "failed";
  result.failures = failures;
}

console.log(JSON.stringify(result, null, 2));
if (failures.length) {
  process.exit(1);
}

async function sampleRecentEndpoint(pathname) {
  const samples = [];
  for (let index = 0; index < sampleCount; index += 1) {
    samples.push(await fetchRecent(pathname));
  }
  const elapsed = samples.map((sample) => sample.elapsedMs);
  return {
    samples: samples.map(withoutCursor),
    p95Ms: percentile(elapsed, 95),
    maxMs: Math.max(...elapsed),
    returnedCounts: samples.map((sample) => sample.returned),
    latestStartedAt: samples[0]?.latestStartedAt || null,
  };
}

async function sampleCursorEndpoint(pathname) {
  const samples = [];
  for (let index = 0; index < sampleCount; index += 1) {
    const first = await fetchRecent(pathname);
    if (!first.nextCursor) {
      throw new Error("recent clips response did not provide a next_cursor");
    }
    const cursorUrl = new URL(pathname, baseUrl);
    cursorUrl.searchParams.set("cursor", first.nextCursor);
    samples.push(await fetchRecent(`${cursorUrl.pathname}${cursorUrl.search}`));
  }
  const elapsed = samples.map((sample) => sample.elapsedMs);
  return {
    samples: samples.map(withoutCursor),
    p95Ms: percentile(elapsed, 95),
    maxMs: Math.max(...elapsed),
    returnedCounts: samples.map((sample) => sample.returned),
    latestStartedAt: samples[0]?.latestStartedAt || null,
  };
}

async function fetchRecent(pathname) {
  const url = new URL(pathname, baseUrl);
  url.searchParams.set("_slo", `${Date.now()}-${Math.random().toString(16).slice(2)}`);
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), requestTimeoutMs);
  const started = performance.now();
  try {
    const response = await fetch(url, {
      cache: "no-store",
      signal: controller.signal,
    });
    const elapsedMs = Math.round(performance.now() - started);
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    return {
      elapsedMs,
      status: response.status,
      returned: Array.isArray(payload.clips) ? payload.clips.length : 0,
      latestStartedAt: payload.latest_playable_started_at || null,
      firstChannel: payload.clips?.[0]?.channel || null,
      clipCount: payload.clip_count,
      nextCursor: payload.next_cursor || null,
    };
  } finally {
    clearTimeout(timeout);
  }
}

async function measureMobileLiveInteraction() {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({
    viewport: { width: 390, height: 844 },
    isMobile: true,
    hasTouch: true,
  });
  const errors = [];
  let mobileClipReadyMs = null;
  let loadMoreReadyMs = null;
  let oldestBatchReadyMs = null;
  let clipAllButTrafficReadyMs = null;
  let allButTrafficSelectorReadyMs = null;
  let allButTrafficQueueReadyMs = null;
  let state = {};
  page.on("pageerror", (error) => errors.push(sanitizeBrowserMessage(String(error))));
  page.on("console", (message) => {
    if (["error", "warning"].includes(message.type())) {
      errors.push(`${message.type()}: ${sanitizeBrowserMessage(message.text())}`);
    }
  });
  try {
    const started = performance.now();
    await page.goto(`${baseUrl}/?_slo=${Date.now()}`, {
      waitUntil: "domcontentloaded",
      timeout: requestTimeoutMs,
    });
    await page.waitForSelector("#clips .clip-card", {
      state: "visible",
      timeout: budgets.mobileClipReadyMs,
    });
    mobileClipReadyMs = Math.round(performance.now() - started);

    const loadMoreStarted = performance.now();
    await page.locator(".clip-load-more-sentinel").evaluate((node) => {
      node.scrollIntoView({ block: "center" });
    });
    await page.waitForFunction(
      () => {
        const clipList = document.querySelector("#clips");
        return (
          clipList?.getAttribute("aria-busy") === "false" &&
          document.querySelectorAll("#clips .clip-card").length >= 48
        );
      },
      null,
      { timeout: budgets.loadMoreReadyMs },
    );
    loadMoreReadyMs = Math.round(performance.now() - loadMoreStarted);

    const oldestStarted = performance.now();
    await page
      .locator("#clip-display-controls")
      .getByRole("button", { name: "Oldest", exact: true })
      .click();
    await page.waitForFunction(
      () => {
        const clipList = document.querySelector("#clips");
        const oldestButton = [...document.querySelectorAll("#clip-display-controls button")]
          .find((button) => button.textContent?.trim() === "Oldest");
        return (
          oldestButton?.getAttribute("aria-pressed") === "true" &&
          clipList?.getAttribute("aria-busy") === "false" &&
          document.querySelectorAll("#clips .clip-card").length > 0
        );
      },
      null,
      { timeout: budgets.oldestBatchReadyMs },
    );
    oldestBatchReadyMs = Math.round(performance.now() - oldestStarted);
    await page
      .locator("#clip-display-controls")
      .getByRole("button", { name: "Newest", exact: true })
      .click();
    await page.waitForFunction(
      () => {
        const newestButton = [...document.querySelectorAll("#clip-display-controls button")]
          .find((button) => button.textContent?.trim() === "Newest");
        return (
          newestButton?.getAttribute("aria-pressed") === "true" &&
          document.querySelector("#clips")?.getAttribute("aria-busy") === "false"
        );
      },
      null,
      { timeout: requestTimeoutMs },
    );

    const clipFilterStarted = performance.now();
    await page.locator("#channel-filter details").evaluate((details) => {
      details.open = true;
    });
    await page
      .locator("#channel-filter")
      .getByRole("button", { name: /All but traffic/i })
      .click();
    await page.waitForFunction(
      () => {
        const clipList = document.querySelector("#clips");
        const cards = [...document.querySelectorAll("#clips .clip-card")];
        return (
          clipList?.getAttribute("aria-busy") === "false" &&
          cards.length > 0 &&
          cards.every((card) => !(card.textContent || "").includes("VHF 14"))
        );
      },
      null,
      { timeout: budgets.clipAllButTrafficReadyMs },
    );
    clipAllButTrafficReadyMs = Math.round(performance.now() - clipFilterStarted);

    await page.getByRole("tab", { name: "Listen live" }).click();
    const selectorStarted = performance.now();
    await page
      .locator("#live-primary-channel-picker")
      .getByRole("button", { name: "All but Traffic" })
      .waitFor({
        state: "visible",
        timeout: budgets.allButTrafficSelectorReadyMs,
      });
    allButTrafficSelectorReadyMs = Math.round(
      performance.now() - selectorStarted,
    );

    const interactionStarted = performance.now();
    await page
      .locator("#live-primary-channel-picker")
      .getByRole("button", { name: "All but Traffic" })
      .click();
    await page.locator("#panel-live").getByRole("button", { name: "Play" }).click();
    await page.waitForFunction(
      () => {
        const queueText = document.querySelector("#live-queue")?.textContent || "";
        const src = document.querySelector("#live-audio")?.getAttribute("src") || "";
        const activeMode = document.querySelector("#live-channel")?.textContent?.trim() || "";
        return (
          activeMode === "All but Traffic" &&
          queueText.includes("Now playing") &&
          src.includes("/api/clips/audio?channel=") &&
          !src.includes("channel=14")
        );
      },
      null,
      { timeout: budgets.allButTrafficQueueReadyMs },
    );
    allButTrafficQueueReadyMs = Math.round(
      performance.now() - interactionStarted,
    );
  } catch (error) {
    errors.push(sanitizeBrowserMessage(error instanceof Error ? error.message : String(error)));
  } finally {
    state = await captureBrowserState(page);
    await browser.close();
  }
    return {
      mobileClipReadyMs,
      loadMoreReadyMs,
      oldestBatchReadyMs,
      clipAllButTrafficReadyMs,
      allButTrafficSelectorReadyMs,
      allButTrafficQueueReadyMs,
      state,
      errors,
    };
}

function assertP95(label, measurement, budgetMs) {
  if (measurement.p95Ms <= budgetMs) {
    return [];
  }
  return [`${label} p95 ${measurement.p95Ms}ms exceeded ${budgetMs}ms`];
}

function withoutCursor({ nextCursor: _nextCursor, ...sample }) {
  return sample;
}

function assertMax(label, actualMs, budgetMs) {
  if (Number.isFinite(actualMs) && actualMs <= budgetMs) {
    return [];
  }
  return [`${label} ${formatMeasurement(actualMs)} exceeded ${budgetMs}ms`];
}

async function captureBrowserState(page) {
  try {
    return await page.evaluate(() => {
      const sameOriginAudioPath = (rawSrc) => {
        if (!rawSrc) {
          return "";
        }
        try {
          const url = new URL(rawSrc, window.location.href);
          if (url.origin === window.location.origin && url.pathname === "/api/clips/audio") {
            const channel = url.searchParams.get("channel") || "";
            return `${url.pathname}?channel=${channel}`;
          }
          return `${url.origin}${url.pathname}`;
        } catch {
          return "";
        }
      };
      return {
        activeTab: document.querySelector(".tab.is-active")?.textContent?.trim() || "",
        activeClipSort:
          [...document.querySelectorAll("#clip-display-controls button")]
            .find(
              (button) =>
                button.getAttribute("aria-pressed") === "true" &&
                ["Newest", "Oldest"].includes(button.textContent?.trim() || ""),
            )
            ?.textContent?.trim() || "",
        clipListBusy: document.querySelector("#clips")?.getAttribute("aria-busy") || "",
        clipStatus: document.querySelector("#clip-status")?.textContent?.trim() || "",
        loadMoreState:
          document.querySelector("#clip-pagination .clip-load-more-button")?.textContent?.trim() || "",
        clipCards: document.querySelectorAll("#clips .clip-card").length,
        clipCardChannels: [...document.querySelectorAll("#clips .clip-card .channel-pill")]
          .slice(0, 6)
          .map((pill) => pill.textContent?.trim() || ""),
        activeMode: document.querySelector("#live-channel")?.textContent?.trim() || "",
        queue: document.querySelector("#live-queue")?.textContent?.trim() || "",
        audioPath: sameOriginAudioPath(document.querySelector("#live-audio")?.getAttribute("src") || ""),
      };
    });
  } catch (error) {
    return { captureError: sanitizeBrowserMessage(error instanceof Error ? error.message : String(error)) };
  }
}

function formatMeasurement(value) {
  return Number.isFinite(value) ? `${value}ms` : "not reached";
}

function percentile(values, percentileValue) {
  const sorted = [...values].sort((left, right) => left - right);
  const index = Math.min(
    sorted.length - 1,
    Math.max(0, Math.ceil((percentileValue / 100) * sorted.length) - 1),
  );
  return sorted[index] || 0;
}

function normalizeBaseUrl(value) {
  return value.replace(/\/+$/, "");
}

function sanitizeBrowserMessage(message) {
  return message
    .replace(/https:\/\/[^'")\s]+/g, (url) => {
      try {
        const parsed = new URL(url);
        return `${parsed.origin}${parsed.pathname}`;
      } catch {
        return "[url]";
      }
    })
    .replace(/[?&](AWSAccessKeyId|Signature|Expires|X-Amz-[^=\s]+)=[^&'")\s]+/g, "")
    .slice(0, 300);
}

function envNumber(name, fallback) {
  const value = Number(process.env[name]);
  return Number.isFinite(value) && value > 0 ? value : fallback;
}
