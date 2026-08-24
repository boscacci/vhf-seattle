#!/usr/bin/env node
import { performance } from "node:perf_hooks";
import { chromium } from "playwright";

const baseUrl = String(
  process.env.TALKINGBOATS_SEARCH_SMOKE_BASE_URL || "https://seattleboatradio.com",
).replace(/\/+$/, "");
const query = process.env.TALKINGBOATS_SEARCH_SMOKE_QUERY || "Wenatchee";
const routeDelayMs = 500;
const timeoutMs = 15_000;
const viewports = [
  { name: "mobile", viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true },
  { name: "desktop", viewport: { width: 1280, height: 900 } },
];

const browser = await chromium.launch({ headless: true });
const checks = [];
try {
  for (const target of viewports) {
    checks.push(await checkViewport(target));
  }
} finally {
  await browser.close();
}
console.log(JSON.stringify({ status: "ok", baseUrl, query, checks }, null, 2));

async function checkViewport(target) {
  const context = await browser.newContext({
    viewport: target.viewport,
    isMobile: target.isMobile,
    hasTouch: target.hasTouch,
  });
  const errors = [];
  try {
    const page = await context.newPage();
    page.on("console", (message) => {
      if (["error", "warning"].includes(message.type())) {
        errors.push(`console ${message.type()}: ${message.text()}`);
      }
    });
    page.on("pageerror", (error) => errors.push(`page: ${error.message}`));
    await page.goto(`${baseUrl}/search/`, { waitUntil: "domcontentloaded", timeout: timeoutMs });

    const queryInput = page.getByLabel("Search transcript meaning");
    await queryInput.fill(query);
    const firstResponsePromise = page.waitForResponse(searchResponse("7d"), { timeout: timeoutMs });
    const firstStarted = performance.now();
    await page.getByRole("button", { name: "Search clips", exact: true }).click();
    const firstResponse = await firstResponsePromise;
    const firstPayload = await checkedPayload(firstResponse);
    await waitForSettledResults(page);
    const firstElapsedMs = Math.round(performance.now() - firstStarted);
    const firstState = await browserState(page);
    assertResultContract(firstPayload, firstState);
    if (!firstPayload.results.length) {
      throw new Error(`${target.name}: ${query} returned no 7d results`);
    }
    if (
      query.toLowerCase() === "wenatchee" &&
      firstPayload.results.some(
        (result) => !String(result.transcript || "").toLowerCase().includes("wenatchee"),
      )
    ) {
      throw new Error(`${target.name}: 7d Wenatchee search contained an unrelated transcript`);
    }

    let apiElapsedMs = null;
    await page.route("**/api/clips/search**", async (route) => {
      const requestUrl = new URL(route.request().url());
      if (requestUrl.searchParams.get("recency") !== "24h") {
        await route.continue();
        return;
      }
      const started = performance.now();
      const response = await route.fetch({ timeout: timeoutMs });
      apiElapsedMs = Math.round(performance.now() - started);
      await new Promise((resolve) => setTimeout(resolve, routeDelayMs));
      await route.fulfill({ response });
    });
    const secondResponsePromise = page.waitForResponse(searchResponse("24h"), {
      timeout: timeoutMs + routeDelayMs,
    });
    await page
      .locator("#clip-search-recency")
      .getByRole("button", { name: "24h", exact: true })
      .click();
    const inFlightState = await browserState(page);
    if (
      inFlightState.activeRecency !== "24h" ||
      inFlightState.pressed24h !== "true" ||
      inFlightState.status !== "Searching clips..."
    ) {
      throw new Error(
        `${target.name}: 24h state did not update before response: ${JSON.stringify(inFlightState)}`,
      );
    }
    const secondResponse = await secondResponsePromise;
    const secondPayload = await checkedPayload(secondResponse);
    await waitForSettledResults(page);
    const settledState = await browserState(page);
    assertResultContract(secondPayload, settledState);
    if (settledState.activeRecency !== "24h" || settledState.pressed24h !== "true") {
      throw new Error(`${target.name}: 24h state was lost after response`);
    }
    if (!secondPayload.results.length && !settledState.emptyText.includes("No matching clips")) {
      throw new Error(`${target.name}: zero-result search did not render an explicit empty state`);
    }
    if (errors.length) {
      throw new Error(`${target.name}: browser errors: ${errors.join(" | ")}`);
    }
    const screenshot = `/tmp/talkingboats-search-24h-prod-${target.name}.png`;
    await page.screenshot({ path: screenshot, fullPage: true });
    return {
      viewport: target.name,
      firstElapsedMs,
      firstResultCount: firstPayload.results.length,
      api24hElapsedMs: apiElapsedMs,
      result24hCount: secondPayload.results.length,
      inFlightState,
      settledState,
      screenshot,
    };
  } finally {
    await context.close();
  }
}

function searchResponse(recency) {
  return (response) => {
    const url = new URL(response.url());
    return url.pathname === "/api/clips/search" && url.searchParams.get("recency") === recency;
  };
}

async function checkedPayload(response) {
  if (!response.ok()) {
    throw new Error(`search returned HTTP ${response.status()}`);
  }
  return response.json();
}

async function waitForSettledResults(page) {
  await page.waitForFunction(
    () => document.querySelector("#clip-search-results")?.getAttribute("aria-busy") !== "true",
    null,
    { timeout: timeoutMs },
  );
}

async function browserState(page) {
  return page.evaluate(() => ({
    activeRecency:
      document.querySelector("#clip-search-recency .is-active")?.textContent?.trim() || "",
    pressed24h:
      [...document.querySelectorAll("#clip-search-recency button")]
        .find((button) => button.textContent?.trim() === "24h")
        ?.getAttribute("aria-pressed") || "",
    status: document.querySelector("#clip-search-status")?.textContent || "",
    resultCount: document.querySelectorAll("#clip-search-results .search-result-card").length,
    emptyText: document.querySelector("#clip-search-results .muted-inline")?.textContent || "",
  }));
}

function assertResultContract(payload, state) {
  const results = Array.isArray(payload.results) ? payload.results : [];
  const minimumScore = Number(payload.minimum_score ?? 0.35);
  if (results.length !== state.resultCount) {
    throw new Error(`API/browser result counts differ: ${results.length} != ${state.resultCount}`);
  }
  if (results.some((result) => Number(result.score) < minimumScore)) {
    throw new Error(`search returned a result below minimum score ${minimumScore}`);
  }
}
