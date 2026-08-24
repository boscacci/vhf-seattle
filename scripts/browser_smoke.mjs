#!/usr/bin/env node
import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import { extname, join, normalize } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const repoRoot = fileURLToPath(new URL("..", import.meta.url));
const publicSiteRoot = join(repoRoot, "public-site");
const audioStartedAt = new Date(Date.now() - 30_000).toISOString();
let longLiveQueueClipAudio = false;
let injectLiveQueueRaceClip = false;
let returnStaleLiveQueue = false;
let servedStaleLiveQueue = false;
let returnMixedAgeLiveQueue = false;
let servedMixedAgeLiveQueue = false;
let returnEmptyLiveQueue = false;
let liveQueueRecentRequests = 0;
let failLiveQueueRecentRequests = 0;
let holdRecentClipResponses = false;
let releaseRecentClipResponses = [];
let holdFeatureClipResponses = false;
let releaseFeatureClipResponses = [];
let aisShipRequests = 0;
let aisViewerHeadRequests = 0;
let topicClusterReturnsNotFound = false;
let injectFreshRecentClip = false;
let freshRecentClipSequence = 0;
const recentClipRequestUrls = [];
const featuredClipIndexes = new Set([1, 7, 13, 49, 91]);
const mimeTypes = {
  ".css": "text/css; charset=utf-8",
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".svg": "image/svg+xml",
};

const server = createServer(async (request, response) => {
  try {
    const url = new URL(request.url || "/", "http://127.0.0.1");
    if (url.pathname === "/api/analysis/lexical") {
      return sendJson(response, lexicalPayload());
    }
    if (url.pathname === "/api/clips/audio") {
      return sendBytes(
        response,
        longLiveQueueClipAudio
          ? wavSilence({ durationSeconds: 8 })
          : wavTestSignal({ durationSeconds: 3 }),
        "audio/wav",
      );
    }
    if (/^\/clips\/[^/]+\.(mp3|wav|m4a|ogg)$/i.test(url.pathname)) {
      return sendBytes(response, wavTestSignal({ durationSeconds: 3 }), "audio/wav");
    }
    if (url.pathname === "/api/live/current.mp3") {
      return sendBytes(response, wavSilence({ durationSeconds: 1 }), "audio/wav");
    }
    if (url.pathname === "/api/clips/recent") {
      recentClipRequestUrls.push(new URL(url.href));
      if (isLiveQueueRecentRequest(url) && failLiveQueueRecentRequests > 0) {
        failLiveQueueRecentRequests -= 1;
        return sendJson(response, { detail: "private API unavailable" }, 504);
      }
      if (holdRecentClipResponses) {
        await new Promise((resolve) => {
          releaseRecentClipResponses.push(resolve);
        });
      }
      return sendJson(response, recentClipPayload(url));
    }
    if (url.pathname === "/api/clips/features" && request.method === "POST") {
      if (request.headers["x-talkingboats-tailnet-dev"] !== "1") {
        return sendJson(response, { detail: "tailnet operator access required" }, 403);
      }
      if (holdFeatureClipResponses) {
        await new Promise((resolve) => {
          releaseFeatureClipResponses.push(resolve);
        });
      }
      return sendJson(response, await clipFeaturePayload(request));
    }
    if (url.pathname === "/api/clips/search") {
      return sendJson(response, searchPayload(url));
    }
    if (url.pathname === "/api/live/performance") {
      return sendJson(response, performancePayload());
    }
    if (url.pathname === "/api/live/channels") {
      return sendJson(response, liveChannelsPayload());
    }
    if (url.pathname === "/ais-catcher/ships.json") {
      aisShipRequests += 1;
      return sendJson(response, {
        count: 2,
        ships: [{ MMSI: 367000001 }, { MMSI: 367000002 }],
      });
    }
    if (url.pathname === "/ais-catcher/" || url.pathname === "/ais-catcher") {
      if (request.method === "HEAD") {
        aisViewerHeadRequests += 1;
        return sendJson(response, { detail: "upstream viewer does not answer HEAD" }, 504);
      }
      return sendHtml(response, "<html><body>AIS-catcher map</body></html>");
    }
    if (url.pathname === "/recent_clips.json" || url.pathname === "/public_manifest.json") {
      return sendJson(response, publishedManifestPayload());
    }
    if (url.pathname === "/analysis/topic_clusters.html") {
      if (topicClusterReturnsNotFound) {
        return sendJson(response, { detail: "asset not found" }, 404);
      }
      return sendHtml(
        response,
        `<!doctype html><html><body data-topic-rotation="waiting">topic clusters
<script>
window.addEventListener("message", (event) => {
  if (event.data?.type === "talkingboats-topic-plot-rotation") {
    document.body.dataset.topicRotation = event.data.enabled ? "running" : "stopped";
  }
});
</script>
</body></html>`,
      );
    }
    return sendStatic(response, url.pathname);
  } catch (error) {
    response.writeHead(500, { "content-type": "text/plain; charset=utf-8" });
    response.end(error instanceof Error ? error.message : String(error));
  }
});

try {
  const { port } = await listen(server);
  const baseUrl = `http://127.0.0.1:${port}`;
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: { width: 390, height: 844 },
    isMobile: true,
    hasTouch: true,
  });
  try {
    const page = await context.newPage();
    holdRecentClipResponses = true;
    await page.goto(`${baseUrl}/clips/`);
    await page.locator("#clips .clip-card").first().waitFor({ state: "visible", timeout: 10000 });
    const lazyClipShell = await page.evaluate(() => ({
      busy: document.querySelector("#clips")?.getAttribute("aria-busy"),
      placeholderCount: document.querySelectorAll("#clips .clip-placeholder").length,
      clipCount: document.querySelectorAll("#clips .clip-card").length,
      firstTranscript:
        document.querySelector("#clips .clip-card:first-child blockquote")?.textContent || "",
      controlsText: document.querySelector("#clip-display-controls")?.textContent || "",
      status: document.querySelector("#clip-status")?.textContent || "",
    }));
    if (lazyClipShell.busy !== "true") {
      throw new Error(`recent clip list did not mark itself busy while lazy-loading: ${JSON.stringify(lazyClipShell)}`);
    }
    if (
      lazyClipShell.placeholderCount !== 0 ||
      lazyClipShell.clipCount === 0 ||
      !lazyClipShell.firstTranscript.includes("Smoke clip")
    ) {
      throw new Error(`published clips did not hide live latency: ${JSON.stringify(lazyClipShell)}`);
    }
    if (
      !lazyClipShell.controlsText.includes("Show clips") ||
      !lazyClipShell.controlsText.includes("Flip page order") ||
      lazyClipShell.controlsText.includes("Clips per page")
    ) {
      throw new Error(`recent clip controls were not available during lazy load: ${JSON.stringify(lazyClipShell)}`);
    }
    if (!lazyClipShell.status.includes("refreshing")) {
      throw new Error(`recent clip background-refresh status was not clear: ${JSON.stringify(lazyClipShell)}`);
    }
    const initialClipRequest = recentClipRequestUrls[0];
    if (
      initialClipRequest?.searchParams.get("include_counts") !== "false" ||
      initialClipRequest?.searchParams.get("include_playback_url") !== "false" ||
      initialClipRequest?.searchParams.get("verify_playback_exists") !== "false"
    ) {
      throw new Error(`initial clip request was not on the fast path: ${initialClipRequest?.href}`);
    }
    holdRecentClipResponses = false;
    releaseRecentClipResponses.splice(0).forEach((release) => release());
    await page.waitForFunction(
      () =>
        document.querySelector("#clips")?.getAttribute("aria-busy") === "false" &&
        (document.querySelector("#clips .clip-card:first-child blockquote")?.textContent || "").includes(
          "Smoke clip",
        ),
    );
    const mobileClipPlayButton = page
      .locator("#clips .clip-card:first-child")
      .getByRole("button", { name: "Play clip", exact: true });
    const mobileClipProgress = page.locator(
      "#clips .clip-card:first-child .clip-progress-input",
    );
    const mobileClipWaveform = page.locator(
      "#clips .clip-card:first-child .clip-waveform-canvas",
    );
    await mobileClipWaveform.scrollIntoViewIfNeeded();
    await page.waitForFunction(
      () =>
        document
          .querySelector("#clips .clip-card:first-child .clip-waveform-canvas")
          ?.getAttribute("data-waveform-status") === "ready",
      null,
      { timeout: 10000 },
    );
    const mobileClipPlayerTouchTarget = await mobileClipPlayButton.evaluate((button) => {
        const bounds = button.getBoundingClientRect();
        return {
          height: bounds.height,
          width: bounds.width,
        };
      });
    if (
      mobileClipPlayerTouchTarget.height < 56 ||
      mobileClipPlayerTouchTarget.width < 72
    ) {
      throw new Error(
        `mobile clip play target is too small: ${JSON.stringify(mobileClipPlayerTouchTarget)}`,
      );
    }
    const mobileClipProgressState = await mobileClipProgress.evaluate((progress) => {
      const bounds = progress.getBoundingClientRect();
      return {
        ariaLabel: progress.getAttribute("aria-label"),
        height: bounds.height,
        type: progress.getAttribute("type"),
        width: bounds.width,
      };
    });
    if (
      mobileClipProgressState.type !== "range" ||
      mobileClipProgressState.ariaLabel !== "Clip playback position" ||
      mobileClipProgressState.width < 80 ||
      mobileClipProgressState.height < 36
    ) {
      throw new Error(
        `mobile clip progress control is not usable: ${JSON.stringify(mobileClipProgressState)}`,
      );
    }
    const mobileWaveformState = await mobileClipWaveform.evaluate((canvas) => {
      const bounds = canvas.getBoundingClientRect();
      const context = canvas.getContext("2d");
      const pixels = context?.getImageData(0, 0, canvas.width, canvas.height).data || [];
      let coloredPixels = 0;
      for (let index = 3; index < pixels.length; index += 4) {
        if (pixels[index] > 0) {
          coloredPixels += 1;
        }
      }
      return {
        coloredPixels,
        height: bounds.height,
        status: canvas.dataset.waveformStatus,
        width: bounds.width,
      };
    });
    if (
      mobileWaveformState.status !== "ready" ||
      mobileWaveformState.width < 80 ||
      mobileWaveformState.height < 52 ||
      mobileWaveformState.coloredPixels < 100
    ) {
      throw new Error(
        `mobile clip waveform did not render actual audio: ${JSON.stringify(mobileWaveformState)}`,
      );
    }
    await mobileClipPlayButton.click();
    await page.waitForFunction(
      () =>
        !document.querySelector("#clips .clip-card:first-child audio")?.paused &&
        document
          .querySelector("#clips .clip-card:first-child .clip-play-button")
          ?.getAttribute("aria-label") === "Pause clip",
      null,
      { timeout: 5000 },
    );
    await mobileClipProgress.evaluate((progress) => {
      progress.value = String(Number(progress.max) / 2);
      progress.dispatchEvent(new Event("input", { bubbles: true }));
    });
    await page.waitForFunction(
      () => {
        const audio = document.querySelector("#clips .clip-card:first-child audio");
        const progress = document.querySelector(
          "#clips .clip-card:first-child .clip-progress-input",
        );
        const time = document.querySelector(
          "#clips .clip-card:first-child .example-player-time",
        );
        return (
          audio instanceof HTMLAudioElement &&
          Number(audio.currentTime) > 0 &&
          Number(progress?.value) > 0 &&
          (time?.textContent || "").includes(" / ")
        );
      },
      null,
      { timeout: 5000 },
    );
    await page.getByRole("button", { name: "Pause clip", exact: true }).click();
    await page.waitForFunction(
      () =>
        document.querySelector("#clips .clip-card:first-child audio")?.paused &&
        document
          .querySelector("#clips .clip-card:first-child .clip-play-button")
          ?.getAttribute("aria-label") === "Play clip",
      null,
      { timeout: 5000 },
    );
    const desktopClipContext = await browser.newContext({ viewport: { width: 1280, height: 900 } });
    try {
      const desktopClipPage = await desktopClipContext.newPage();
      await desktopClipPage.goto(`${baseUrl}/clips/`);
      const desktopClipAudio = desktopClipPage.locator("#clips .clip-card:first-child audio");
      const desktopClipPlayButton = desktopClipPage
        .locator("#clips .clip-card:first-child")
        .getByRole("button", { name: "Play clip", exact: true });
      const desktopClipProgress = desktopClipPage.locator(
        "#clips .clip-card:first-child .clip-progress-input",
      );
      const desktopClipWaveform = desktopClipPage.locator(
        "#clips .clip-card:first-child .clip-waveform-canvas",
      );
      await desktopClipPlayButton.waitFor({ state: "visible", timeout: 10000 });
      await desktopClipPage.waitForFunction(
        () =>
          document
            .querySelector("#clips .clip-card:first-child .clip-waveform-canvas")
            ?.getAttribute("data-waveform-status") === "ready",
        null,
        { timeout: 10000 },
      );
      const desktopClipPlayerTarget = await desktopClipPlayButton.evaluate((button) => {
        const bounds = button.getBoundingClientRect();
        return { height: bounds.height, width: bounds.width };
      });
      if (
        desktopClipPlayerTarget.height < 56 ||
        desktopClipPlayerTarget.width < 72
      ) {
        throw new Error(
          `desktop clip play target is too small: ${JSON.stringify(desktopClipPlayerTarget)}`,
        );
      }
      const desktopClipProgressWidth = await desktopClipProgress.evaluate(
        (progress) => progress.getBoundingClientRect().width,
      );
      const desktopWaveformState = await desktopClipWaveform.evaluate((canvas) => {
        const bounds = canvas.getBoundingClientRect();
        const playerWidth =
          canvas.closest(".example-player")?.getBoundingClientRect().width || 0;
        return {
          height: bounds.height,
          playerWidth,
          status: canvas.dataset.waveformStatus,
          width: bounds.width,
        };
      });
      if (
        desktopClipProgressWidth < 600 ||
        desktopWaveformState.status !== "ready" ||
        desktopWaveformState.width < 600 ||
        desktopWaveformState.height < 52 ||
        desktopWaveformState.playerWidth < 800
      ) {
        throw new Error(
          `desktop clip waveform does not use available width: ${JSON.stringify({
            desktopClipProgressWidth,
            desktopWaveformState,
          })}`,
        );
      }
      await desktopClipPlayButton.click();
      await desktopClipPage.waitForFunction(
        (audio) => audio instanceof HTMLAudioElement && !audio.paused,
        await desktopClipAudio.elementHandle(),
        { timeout: 5000 },
      );
      await desktopClipProgress.evaluate((progress) => {
        progress.value = String(Number(progress.max) / 2);
        progress.dispatchEvent(new Event("input", { bubbles: true }));
      });
      await desktopClipPage.waitForFunction(
        (audio) => audio instanceof HTMLAudioElement && Number(audio.currentTime) > 0,
        await desktopClipAudio.elementHandle(),
        { timeout: 5000 },
      );
      await desktopClipPage.getByRole("button", { name: "Pause clip", exact: true }).click();
      await desktopClipPage.waitForFunction(
        (audio) => audio instanceof HTMLAudioElement && audio.paused,
        await desktopClipAudio.elementHandle(),
        { timeout: 5000 },
      );
    } finally {
      await desktopClipContext.close();
    }
    const recentRequestsBeforeRefresh = recentClipRequestUrls.length;
    injectFreshRecentClip = true;
    await page.getByRole("button", { name: "Refresh" }).click();
    await page.waitForFunction(() =>
      (document.querySelector("#clips .clip-card:first-child blockquote")?.textContent || "").includes(
        "Fresh live clip",
      ),
    );
    const freshRefreshState = await page.evaluate(() => ({
      firstTranscript:
        document.querySelector("#clips .clip-card:first-child blockquote")?.textContent || "",
      status: document.querySelector("#clip-status")?.textContent || "",
    }));
    if (
      recentClipRequestUrls.length <= recentRequestsBeforeRefresh ||
      !freshRefreshState.firstTranscript.includes("Fresh live clip")
    ) {
      throw new Error(
        `browser refresh did not replace the visible clip from the live API: ${JSON.stringify(freshRefreshState)}`,
      );
    }
    injectFreshRecentClip = false;
    await page.getByRole("button", { name: "Refresh" }).click();
    await page.waitForFunction(() =>
      (document.querySelector("#clips .clip-card:first-child blockquote")?.textContent || "").includes("Smoke clip 1"),
    );
    const devClipFeatureState = await page.evaluate(() => ({
      firstTranscript: document.querySelector("#clips .clip-card:first-child blockquote")?.textContent || "",
      buttonText:
        document.querySelector("#clips .clip-card:first-child .feature-clip-button")?.textContent?.trim() || "",
      buttonLabel:
        document.querySelector("#clips .clip-card:first-child .feature-clip-button")?.getAttribute("aria-label") || "",
      buttonPressed:
        document.querySelector("#clips .clip-card:first-child .feature-clip-button")?.getAttribute("aria-pressed") ||
        "",
    }));
    if (
      !devClipFeatureState.firstTranscript.includes("Smoke clip 1") ||
      devClipFeatureState.buttonText !== "☆" ||
      devClipFeatureState.buttonLabel !== "Add to Hall of Fame" ||
      devClipFeatureState.buttonPressed !== "false"
    ) {
      throw new Error(`dev clip review star action is not visible: ${JSON.stringify(devClipFeatureState)}`);
    }
    await page.locator("#channel-filter details").evaluate((details) => {
      details.open = true;
    });
    await page.locator('.channel-filter-checkbox[data-channel="14"]').check();
    const datetimeResponse = page.waitForResponse((response) => {
      const responseUrl = new URL(response.url());
      return (
        responseUrl.pathname === "/api/clips/recent" &&
        responseUrl.searchParams.get("around") === "2026-08-15T12:30" &&
        responseUrl.searchParams.getAll("channels").includes("14")
      );
    });
    await page.locator("#clip-datetime-input").fill("2026-08-15T12:30");
    await page.getByRole("button", { name: "Find clips" }).click();
    await datetimeResponse;
    await page.waitForFunction(() => {
      const controls = document.querySelector("#clip-display-controls")?.textContent || "";
      const status = document.querySelector("#clip-status")?.textContent || "";
      return controls.includes("Browse from time") && status.includes("at or before");
    });
    const datetimeNavigatorState = await page.evaluate(() => ({
      controls: document.querySelector("#clip-display-controls")?.textContent || "",
      clearHidden: document.querySelector("#clear-clip-datetime")?.hidden ?? true,
      status: document.querySelector("#clip-status")?.textContent || "",
    }));
    if (
      !datetimeNavigatorState.controls.includes("Browse from time") ||
      !datetimeNavigatorState.controls.includes("Earlier") ||
      !datetimeNavigatorState.controls.includes("Later") ||
      datetimeNavigatorState.clearHidden ||
      !datetimeNavigatorState.status.includes("at or before")
    ) {
      throw new Error(`datetime clip navigator did not activate: ${JSON.stringify(datetimeNavigatorState)}`);
    }
    const laterResponse = page.waitForResponse((response) => {
      const responseUrl = new URL(response.url());
      return (
        responseUrl.pathname === "/api/clips/recent" &&
        responseUrl.searchParams.get("around") === "2026-08-15T12:30" &&
        responseUrl.searchParams.get("sort") === "oldest"
      );
    });
    await page.locator("#clip-display-controls").getByRole("button", { name: "Later" }).click();
    await laterResponse;
    const latestResponse = page.waitForResponse((response) => {
      const responseUrl = new URL(response.url());
      return (
        responseUrl.pathname === "/api/clips/recent" &&
        !responseUrl.searchParams.has("around") &&
        !responseUrl.searchParams.has("sort")
      );
    });
    await page.getByRole("button", { name: "Back to latest" }).click();
    await latestResponse;
    await page.locator("#channel-filter details").evaluate((details) => {
      details.open = true;
    });
    await page.locator("#channel-filter").getByRole("button", { name: /All but traffic/i }).click();
    await page.waitForFunction(() => {
      const cards = [...document.querySelectorAll("#clips .clip-card")];
      return cards.length > 0 && cards.every((card) => !(card.textContent || "").includes("VHF 14"));
    });
    const clipAllButTrafficState = await page.evaluate(() => ({
      triggerSummary: document.querySelector("#channel-filter .channel-filter-trigger-summary")?.textContent || "",
      renderedClips: document.querySelectorAll("#clips .clip-card").length,
      channels: [...document.querySelectorAll("#clips .clip-card .channel-pill")].map(
        (pill) => pill.textContent?.trim() || "",
      ),
    }));
    const allButTrafficRequest = recentClipRequestUrls.at(-1);
    if (
      !allButTrafficRequest ||
      allButTrafficRequest.searchParams.get("exclude_channels") !== "14" ||
      allButTrafficRequest.searchParams.has("channels")
    ) {
      throw new Error(`clip all-but-traffic request did not use exclude_channels: ${allButTrafficRequest?.href || ""}`);
    }
    if (
      !clipAllButTrafficState.triggerSummary.includes("All but traffic") ||
      clipAllButTrafficState.channels.some((channel) => channel.includes("14"))
    ) {
      throw new Error(`clip all-but-traffic preset rendered traffic: ${JSON.stringify(clipAllButTrafficState)}`);
    }
    await page.getByRole("tab", { name: "Listen live" }).click();
    const liveSelectorState = await page.evaluate(() => ({
      primaryLabels: [...document.querySelectorAll("#live-primary-channel-picker .live-channel-option")].map((button) =>
        button.textContent?.trim(),
      ),
      advancedOpen: Boolean(document.querySelector(".live-advanced-channel-selector")?.open),
      advancedChannelButtons: document.querySelectorAll("#live-channel-picker .live-channel-option").length,
    }));
    if (
      liveSelectorState.primaryLabels.join("|") !== "Everything|All but Traffic" ||
      liveSelectorState.advancedOpen ||
      liveSelectorState.advancedChannelButtons < 10
    ) {
      throw new Error(`live channel selector did not render compact controls: ${JSON.stringify(liveSelectorState)}`);
    }
    await page.locator("#live-queue").waitFor({ state: "visible", timeout: 10000 });
    longLiveQueueClipAudio = true;
    injectLiveQueueRaceClip = true;
    liveQueueRecentRequests = 0;
    await page.locator("#panel-live").getByRole("button", { name: "Play" }).click();
    await page.waitForFunction(() => {
      const queueText = document.querySelector("#live-queue")?.textContent || "";
      const liveStatus = document.querySelector("#live-status")?.textContent || "";
      return (
        queueText.includes("Catching up on latest 3 transmissions") &&
        (liveStatus.includes("Catching up") || queueText.includes("Now playing"))
      );
    });
    const liveCatchupState = await page.evaluate(() => ({
      status: document.querySelector("#live-status")?.textContent || "",
      queue: document.querySelector("#live-queue")?.textContent || "",
      src: document.querySelector("#live-audio")?.getAttribute("src") || "",
      playLabel: document.querySelector("#play-live .play-label")?.textContent || "",
    }));
    if (
      !liveCatchupState.queue.includes("Catching up on latest 3 transmissions") ||
      !liveCatchupState.queue.includes("Queued2 transmissions") ||
      !liveCatchupState.src.includes("/api/clips/audio?channel=14&started_at=") ||
      liveCatchupState.playLabel !== "Pause"
    ) {
      throw new Error(`live monitor did not catch up on recent clips: ${JSON.stringify(liveCatchupState)}`);
    }
    await page.waitForTimeout(5500);
    const liveCatchupRaceState = await page.evaluate(() => ({
      status: document.querySelector("#live-status")?.textContent || "",
      queue: document.querySelector("#live-queue")?.textContent || "",
      src: document.querySelector("#live-audio")?.getAttribute("src") || "",
      playLabel: document.querySelector("#play-live .play-label")?.textContent || "",
    }));
    if (
      liveQueueRecentRequests < 2 ||
      !liveCatchupRaceState.queue.includes("Catching up on latest 3 transmissions") ||
      !liveCatchupRaceState.queue.includes("Queued2 transmissions") ||
      liveCatchupRaceState.src.includes("channel=16")
    ) {
      throw new Error(
        `live monitor admitted a realtime queue clip during catch-up: ${JSON.stringify({
          liveQueueRecentRequests,
          liveCatchupRaceState,
        })}`,
      );
    }
    for (let index = 0; index < 3; index += 1) {
      await page.evaluate(() => {
        document.querySelector("#live-audio")?.dispatchEvent(new Event("ended"));
      });
      await page.waitForTimeout(500);
    }
    await page.waitForFunction(() => {
      const queueText = document.querySelector("#live-queue")?.textContent || "";
      const src = document.querySelector("#live-audio")?.getAttribute("src") || "";
      const playLabel = document.querySelector("#play-live .play-label")?.textContent || "";
      return (
        src === "" &&
        document.querySelector("#live-queue")?.hidden === false &&
        playLabel === "Pause" &&
        !queueText.includes("Catching up on latest 3 transmissions") &&
        queueText.includes("Waiting for queued transmission")
      );
    });
    const liveQueueWaitState = await page.evaluate(() => ({
      selectedMode: document.querySelector("#live-channel")?.textContent || "",
      status: document.querySelector("#live-status")?.textContent || "",
      queueHidden: document.querySelector("#live-queue")?.hidden ?? false,
      queue: document.querySelector("#live-queue")?.textContent || "",
      src: document.querySelector("#live-audio")?.getAttribute("src") || "",
      playLabel: document.querySelector("#play-live .play-label")?.textContent || "",
    }));
    if (
      liveQueueWaitState.selectedMode !== "Everything" ||
      liveQueueWaitState.queueHidden ||
      liveQueueWaitState.src !== "" ||
      liveQueueWaitState.playLabel !== "Pause" ||
      !liveQueueWaitState.queue.includes("Waiting for queued transmission")
    ) {
      throw new Error(`live monitor did not wait for queued clips after catch-up: ${JSON.stringify(liveQueueWaitState)}`);
    }
    longLiveQueueClipAudio = false;
    injectLiveQueueRaceClip = false;
    await page.locator("#panel-live").getByRole("button", { name: "Pause" }).click();
    await page.locator("#live-primary-channel-picker").getByRole("button", { name: "Everything" }).click();
    failLiveQueueRecentRequests = 1;
    await page.locator("#panel-live").getByRole("button", { name: "Play" }).click();
    await page.waitForFunction(() => {
      const queueText = document.querySelector("#live-queue")?.textContent || "";
      const src = document.querySelector("#live-audio")?.getAttribute("src") || "";
      return queueText.includes("Catching up on latest 3 transmissions") && src.includes("/clips/");
    });
    const liveManifestFallbackState = await page.evaluate(() => ({
      status: document.querySelector("#live-status")?.textContent || "",
      queue: document.querySelector("#live-queue")?.textContent || "",
      src: document.querySelector("#live-audio")?.getAttribute("src") || "",
      playLabel: document.querySelector("#play-live .play-label")?.textContent || "",
    }));
    if (
      !liveManifestFallbackState.queue.includes("Queued2 transmissions") ||
      !liveManifestFallbackState.src.includes("/clips/") ||
      liveManifestFallbackState.playLabel !== "Pause"
    ) {
      throw new Error(
        `live monitor did not fall back to published clips after live API failure: ${JSON.stringify(liveManifestFallbackState)}`,
      );
    }
    await page.locator("#panel-live").getByRole("button", { name: "Pause" }).click();
    await page.locator("#live-primary-channel-picker").getByRole("button", { name: "All but Traffic" }).click();
    longLiveQueueClipAudio = true;
    await page.locator("#panel-live").getByRole("button", { name: "Play" }).click();
    await page.waitForFunction(() => {
      const queueText = document.querySelector("#live-queue")?.textContent || "";
      const src = document.querySelector("#live-audio")?.getAttribute("src") || "";
      return queueText.includes("All but Traffic mode on") && src.includes("/api/clips/audio?channel=");
    });
    const allButTrafficState = await page.evaluate(() => ({
      selectedMode: document.querySelector("#live-channel")?.textContent || "",
      queue: document.querySelector("#live-queue")?.textContent || "",
      src: document.querySelector("#live-audio")?.getAttribute("src") || "",
      playLabel: document.querySelector("#play-live .play-label")?.textContent || "",
    }));
    if (
      allButTrafficState.selectedMode !== "All but Traffic" ||
      allButTrafficState.src.includes("channel=14") ||
      allButTrafficState.playLabel !== "Pause"
    ) {
      throw new Error(`all-but-traffic live mode did not exclude Seattle Traffic: ${JSON.stringify(allButTrafficState)}`);
    }
    await page.getByRole("tab", { name: /^(Clips|Clip Review)$/ }).click();
    await page.waitForFunction(() => {
      const audio = document.querySelector("#live-audio");
      const src = audio?.getAttribute("src") || "";
      const playLabel = document.querySelector("#play-live .play-label")?.textContent || "";
      return (
        audio instanceof HTMLAudioElement &&
        audio.paused &&
        src === "" &&
        playLabel === "Play"
      );
    });
    const stoppedLiveOnTabLeave = await page.evaluate(() => ({
      paused: document.querySelector("#live-audio")?.paused ?? false,
      src: document.querySelector("#live-audio")?.getAttribute("src") || "",
      playLabel: document.querySelector("#play-live .play-label")?.textContent || "",
    }));
    if (
      !stoppedLiveOnTabLeave.paused ||
      stoppedLiveOnTabLeave.src !== "" ||
      stoppedLiveOnTabLeave.playLabel !== "Play"
    ) {
      throw new Error(
        `leaving Listen live did not stop the active stream: ${JSON.stringify(stoppedLiveOnTabLeave)}`,
      );
    }
    longLiveQueueClipAudio = false;
    await page.goto(`${baseUrl}/analysis/`);
    await page
      .locator("#lexical-analysis .clip-play-button")
      .first()
      .waitFor({ state: "visible", timeout: 10000 });
    await page.waitForFunction(
      () => {
        const activeCard = [...document.querySelectorAll(".language-card")].find((card) =>
          card.textContent?.includes("Analyzed channels"),
        );
        return (
          activeCard?.querySelector("strong")?.textContent === "1 channel"
          && ![...document.querySelectorAll(".channel-bar-label")].some((label) =>
            label.textContent?.includes("VHF 06"),
          )
        );
      },
      null,
      { timeout: 10000 },
    );
    const result = await page.evaluate(async () => {
      const cards = [...document.querySelectorAll(".language-card")];
      const activeCard = cards.find((card) => card.textContent?.includes("Analyzed channels"));
      const transcriptCard = cards.find((card) => card.textContent?.includes("Analyzed transcripts"));
      const audio = document.querySelector("#lexical-analysis audio");
      if (!(audio instanceof HTMLAudioElement)) {
        throw new Error("analysis audio control did not render");
      }
      const topicFrame = document.querySelector(".topic-frame");
      const topicFrameShell = document.querySelector(".topic-frame-shell");
      const topicPanel = [...document.querySelectorAll(".language-panel")].find((panel) =>
        panel.querySelector("h3")?.textContent?.includes("BERTopic transcript clusters"),
      );
      if (!(topicFrame instanceof HTMLIFrameElement)) {
        throw new Error("topic iframe did not render");
      }
      if (!(topicFrameShell instanceof HTMLElement)) {
        throw new Error("topic iframe shell did not render");
      }
      if (!(topicPanel instanceof HTMLElement)) {
        throw new Error("transcript topics panel did not render");
      }
      const topicFrameStyle = window.getComputedStyle(topicFrame);
      const topicFrameBounds = topicFrame.getBoundingClientRect();
      const topicFrameShellStyle = window.getComputedStyle(topicFrameShell);
      const metadata = await new Promise((resolve, reject) => {
        const timeout = window.setTimeout(() => reject(new Error("audio metadata timed out")), 5000);
        audio.addEventListener(
          "loadedmetadata",
          () => {
            window.clearTimeout(timeout);
            resolve({
              duration: audio.duration,
              src: audio.src,
              canPlayWav: audio.canPlayType("audio/wav"),
            });
          },
          { once: true },
        );
        audio.addEventListener(
          "error",
          () => {
            window.clearTimeout(timeout);
            reject(new Error(`audio element error ${audio.error?.code || "unknown"}`));
          },
          { once: true },
        );
        audio.load();
      });
      return {
        activeChannelMetric: activeCard?.querySelector("strong")?.textContent,
        analyzedTranscriptMetric: transcriptCard?.querySelector("strong")?.textContent,
        audioCount: document.querySelectorAll("#lexical-analysis audio").length,
        panelHeadings: [...document.querySelectorAll("#lexical-analysis .language-panel h3")].map(
          (heading) => heading.textContent || "",
        ),
        channelBarLabels: [...document.querySelectorAll(".channel-bar-label")].map(
          (label) => label.textContent || "",
        ),
        topicFrame: {
          allow: topicFrame.getAttribute("allow"),
          allowFullscreen: topicFrame.allowFullscreen,
          height: topicFrameBounds.height,
          src: topicFrame.src,
          touchAction: topicFrameStyle.touchAction,
        },
        topicFrameShell: {
          display: topicFrameShellStyle.display,
        },
        transcriptTopics: {
          title: topicPanel.querySelector("h3")?.textContent,
          topicCards: topicPanel.querySelectorAll(".topic-card").length,
          hasRemovedSummary: Boolean(topicPanel.querySelector(".mobile-nlp-panel, .nlp-summary-grid")),
          bodyText: topicPanel.textContent || "",
        },
        metadata,
      };
    });
    if (result.activeChannelMetric !== "1 channel") {
      throw new Error(`expected active channel metric 1 channel, saw ${result.activeChannelMetric}`);
    }
    if (result.analyzedTranscriptMetric !== "46,668") {
      throw new Error(`expected comma-formatted transcript count, saw ${result.analyzedTranscriptMetric}`);
    }
    if (result.channelBarLabels.some((label) => label.includes("VHF 06"))) {
      throw new Error(`analysis chart included an unlistenable channel: ${JSON.stringify(result.channelBarLabels)}`);
    }
    if (!String(result.metadata.src).includes("/api/clips/audio?channel=14&started_at=")) {
      throw new Error(`analysis audio did not use same-origin clip API: ${result.metadata.src}`);
    }
    if (!Number.isFinite(result.metadata.duration) || result.metadata.duration <= 0) {
      throw new Error(`analysis audio metadata was not playable: ${result.metadata.duration}`);
    }
    if (!String(result.topicFrame.src).endsWith("/analysis/topic_clusters.html")) {
      throw new Error(`topic iframe used unexpected source: ${result.topicFrame.src}`);
    }
    if (!result.topicFrame.allowFullscreen || result.topicFrame.allow !== "fullscreen") {
      throw new Error("topic iframe is not fullscreen-enabled");
    }
    if (result.topicFrameShell.display !== "none") {
      throw new Error(`topic iframe should be hidden on mobile: ${result.topicFrameShell.display}`);
    }
    if (result.transcriptTopics.hasRemovedSummary) {
      throw new Error("removed mobile NLP summary is still present");
    }
    if (result.transcriptTopics.topicCards < 1) {
      throw new Error(`transcript topics did not render topic cards: ${JSON.stringify(result.transcriptTopics)}`);
    }
    if (
      result.panelHeadings.join("|") !==
      "Analyzed transcript clips by VHF channel|BERTopic transcript clusters|Radio words|Suspected vessels and entities|Maritime radio references|Reference index"
    ) {
      throw new Error(`analysis panels rendered in the wrong order: ${JSON.stringify(result.panelHeadings)}`);
    }
    if (!result.transcriptTopics.title.includes("BERTopic") || !result.transcriptTopics.bodyText.includes("3D BERTopic")) {
      throw new Error(`BERTopic cluster label was not clear: ${JSON.stringify(result.transcriptTopics)}`);
    }
    if (result.transcriptTopics.bodyText.includes("Descriptive NLP summary")) {
      throw new Error("removed descriptive NLP copy is still present");
    }
    if (!["pan-x pan-y pinch-zoom", "manipulation"].includes(result.topicFrame.touchAction)) {
      throw new Error(`topic iframe blocks pinch zoom: ${result.topicFrame.touchAction}`);
    }
    const desktopContext = await browser.newContext({ viewport: { width: 1280, height: 900 } });
    try {
      const desktopPage = await desktopContext.newPage();
      await desktopPage.goto(`${baseUrl}/analysis/`);
      await desktopPage.locator(".topic-card").first().waitFor({ state: "visible", timeout: 10000 });
      await desktopPage.waitForFunction(
        () => {
          const frame = document.querySelector(".topic-frame");
          return frame?.contentDocument?.body?.dataset.topicRotation === "running";
        },
        null,
        { timeout: 10000 },
      );
      const runningTopicFrame = await desktopPage.evaluate(() => ({
        rotation: document.querySelector(".topic-frame")?.contentDocument?.body?.dataset.topicRotation || "",
        activeChannelMetric: [...document.querySelectorAll(".language-card")]
          .find((card) => card.textContent?.includes("Analyzed channels"))
          ?.querySelector("strong")?.textContent || "",
        channelBarLabels: [...document.querySelectorAll(".channel-bar-label")].map(
          (label) => label.textContent || "",
        ),
      }));
      if (
        runningTopicFrame.rotation !== "running"
        || runningTopicFrame.activeChannelMetric !== "1 channel"
        || runningTopicFrame.channelBarLabels.some((label) => label.includes("VHF 06"))
      ) {
        throw new Error(`analysis page did not apply live channel or topic rotation state: ${JSON.stringify(runningTopicFrame)}`);
      }
      await desktopPage.getByRole("tab", { name: /^(Clips|Clip Review)$/ }).click();
      await desktopPage.waitForFunction(
        () => document.querySelector(".topic-frame")?.contentDocument?.body?.dataset.topicRotation === "stopped",
        null,
        { timeout: 3000 },
      );
      topicClusterReturnsNotFound = true;
      await desktopPage.goto(`${baseUrl}/analysis/`);
      await desktopPage.locator(".topic-card").first().waitFor({ state: "visible", timeout: 10000 });
      await desktopPage.waitForFunction(
        () => document.querySelector(".topic-frame-shell")?.hidden === true,
        null,
        { timeout: 3000 },
      );
      const unavailableTopicFrame = await desktopPage.evaluate(() => ({
        shellHidden: document.querySelector(".topic-frame-shell")?.hidden || false,
        topicCards: document.querySelectorAll(".topic-card").length,
        bodyText: document.querySelector(".language-panel")?.textContent || "",
      }));
      if (!unavailableTopicFrame.shellHidden || unavailableTopicFrame.topicCards < 1) {
        throw new Error(`unavailable topic iframe was not hidden cleanly: ${JSON.stringify(unavailableTopicFrame)}`);
      }
    } finally {
      await desktopContext.close();
      topicClusterReturnsNotFound = false;
    }
    await page.getByRole("tab", { name: /^(Clips|Clip Review)$/ }).click();
    await page.locator("#clips .clip-card").first().waitFor({ state: "visible", timeout: 10000 });
    await page.evaluate(() => {
      window.__clipAudioBeforeStatsPoll = document.querySelector("#clips .clip-card audio");
    });
    await page.waitForTimeout(11000);
    const clipAudioStableAfterStatsPoll = await page.evaluate(
      () => window.__clipAudioBeforeStatsPoll === document.querySelector("#clips .clip-card audio"),
    );
    if (!clipAudioStableAfterStatsPoll) {
      throw new Error("clip stats polling replaced the existing audio control");
    }
    const initialInfiniteScroll = await page.evaluate(() => ({
      renderedClips: document.querySelectorAll("#clips .clip-card").length,
      loadMoreText:
        document.querySelector("#clip-pagination .clip-load-more-button")?.textContent?.trim() || "",
      hasOldPagination: Boolean(
        document.querySelector(
          "#clip-pagination .pagination-page-button, #clip-pagination .pagination-actions",
        ),
      ),
      controlsText: document.querySelector("#clip-display-controls")?.textContent || "",
    }));
    if (
      initialInfiniteScroll.renderedClips !== 24 ||
      initialInfiniteScroll.loadMoreText !== "Load 24 more" ||
      initialInfiniteScroll.hasOldPagination ||
      initialInfiniteScroll.controlsText.includes("Clips per page")
    ) {
      throw new Error(
        `initial infinite-scroll batch was incorrect: ${JSON.stringify(initialInfiniteScroll)}`,
      );
    }
    await page.evaluate(() => {
      window.__firstClipCardBeforeLoadMore = document.querySelector("#clips .clip-card");
      window.__firstClipAudioBeforeLoadMore = document.querySelector("#clips .clip-card audio");
    });
    await page
      .locator("#clip-pagination")
      .getByRole("button", { name: "Load 24 more", exact: true })
      .click();
    await page.waitForFunction(
      () => document.querySelectorAll("#clips .clip-card").length === 48,
      null,
      { timeout: 10000 },
    );
    await page
      .locator("#clip-pagination")
      .getByRole("button", { name: "Load 24 more", exact: true })
      .click();
    await page.waitForFunction(
      () =>
        document.querySelectorAll("#clips .clip-card").length >= 72 &&
        !document.querySelector("#clip-pagination")?.hasAttribute("aria-busy"),
      null,
      { timeout: 10000 },
    );
    const infiniteScrollState = await page.evaluate(() => ({
      renderedClips: document.querySelectorAll("#clips .clip-card").length,
      firstTranscript: document.querySelector("#clips .clip-card:first-child blockquote")?.textContent || "",
      preservedCard:
        window.__firstClipCardBeforeLoadMore === document.querySelector("#clips .clip-card:first-child"),
      preservedAudio:
        window.__firstClipAudioBeforeLoadMore === document.querySelector("#clips .clip-card:first-child audio"),
      loadMoreText:
        document.querySelector("#clip-pagination .clip-load-more-button")?.textContent?.trim() || "",
    }));
    if (
      infiniteScrollState.renderedClips < 72 ||
      !infiniteScrollState.firstTranscript.includes("Smoke clip 1") ||
      !infiniteScrollState.preservedCard ||
      !infiniteScrollState.preservedAudio ||
      infiniteScrollState.loadMoreText !== "Load 24 more"
    ) {
      throw new Error(
        `infinite scroll did not preserve rendered clip state: ${JSON.stringify(infiniteScrollState)}`,
      );
    }
    await page.locator("#clip-display-controls").getByRole("button", { name: "Hall of fame", exact: true }).click();
    await page.waitForFunction(() => document.querySelector("#clips blockquote")?.textContent?.includes("Smoke clip 2"));
    const hallOfFameState = await page.evaluate(() => ({
      firstTranscript: document.querySelector("#clips blockquote")?.textContent || "",
      renderedClips: document.querySelectorAll("#clips .clip-card").length,
      status: document.querySelector("#clip-status")?.textContent || "",
      featuredPills: document.querySelectorAll("#clips .featured-pill").length,
      activeShowMode: document
        .querySelector("#clip-display-controls .clip-control-group:first-child button[aria-pressed='true']")
        ?.textContent?.trim(),
    }));
    if (
      hallOfFameState.activeShowMode !== "Hall of fame" ||
      hallOfFameState.renderedClips !== featuredClipIndexes.size ||
      hallOfFameState.featuredPills !== featuredClipIndexes.size ||
      !hallOfFameState.status.includes("featured") ||
      !hallOfFameState.firstTranscript.includes("Smoke clip 2")
    ) {
      throw new Error(`hall of fame filter did not show only featured clips: ${JSON.stringify(hallOfFameState)}`);
    }
    await page.locator("#clip-display-controls").getByRole("button", { name: "Recent", exact: true }).click();
    await page.waitForFunction(() => document.querySelector("#clips blockquote")?.textContent?.includes("Smoke clip 1"));
    const clipControlsBeforeFlip = await page.evaluate(() => {
      const headerControls = document.querySelector("#clip-display-controls");
      const inlineControls = document.querySelector("#clips .clip-display-controls-inline");
      const firstTranscript = document.querySelector("#clips blockquote")?.textContent || "";
      if (!(headerControls instanceof HTMLElement)) {
        throw new Error("clip display controls did not render");
      }
      const controlStyle = window.getComputedStyle(headerControls);
      return {
        display: controlStyle.display,
        inlineControlsPresent: Boolean(inlineControls),
        firstTranscript,
        renderedClips: document.querySelectorAll("#clips .clip-card").length,
        pageStatus: document.querySelector("#clip-pagination")?.textContent || "",
        buttonLabels: [...headerControls.querySelectorAll("button")].map((button) =>
          button.textContent?.trim(),
        ),
      };
    });
    if (
      clipControlsBeforeFlip.renderedClips !== 24 ||
      !clipControlsBeforeFlip.firstTranscript.includes("Smoke clip 1")
    ) {
      throw new Error(`recent filter did not reset to one 24-clip batch: ${JSON.stringify(clipControlsBeforeFlip)}`);
    }
    await page.locator("#clip-display-controls").getByRole("button", { name: "Oldest", exact: true }).click();
    await page.waitForFunction(
      () => {
        const activeControl = [...document.querySelectorAll("#clip-display-controls button")]
          .find((button) => button.textContent?.trim() === "Oldest")
          ?.getAttribute("aria-pressed");
        return (
          activeControl === "true" &&
          document.querySelector("#clips")?.getAttribute("aria-busy") === "false" &&
          document.querySelector("#clips blockquote")?.textContent?.includes("Smoke clip 144")
        );
      },
      null,
      { timeout: 10000 },
    );
    const clipControlsAfterFlip = await page.evaluate(() => ({
      firstTranscript: document.querySelector("#clips blockquote")?.textContent || "",
      pageStatus: document.querySelector("#clip-pagination")?.textContent || "",
      renderedClips: document.querySelectorAll("#clips .clip-card").length,
      activeControl: [...document.querySelectorAll("#clip-display-controls button")]
        .find((button) => button.textContent?.trim() === "Oldest")
        ?.getAttribute("aria-pressed"),
    }));
    if (clipControlsBeforeFlip.display !== "grid") {
      throw new Error(`mobile clip controls are not in a grid: ${clipControlsBeforeFlip.display}`);
    }
    if (clipControlsBeforeFlip.inlineControlsPresent) {
      throw new Error(`mobile clip controls were duplicated in the clip list: ${JSON.stringify(clipControlsBeforeFlip)}`);
    }
    if (
      clipControlsBeforeFlip.buttonLabels.includes("24") ||
      clipControlsBeforeFlip.buttonLabels.includes("48")
    ) {
      throw new Error(`removed page-size controls are still visible: ${JSON.stringify(clipControlsBeforeFlip)}`);
    }
    if (
      !clipControlsBeforeFlip.buttonLabels.includes("Hall of fame") ||
      !clipControlsBeforeFlip.buttonLabels.includes("Recent")
    ) {
      throw new Error(`mobile hall of fame filter controls are missing: ${JSON.stringify(clipControlsBeforeFlip)}`);
    }
    if (!clipControlsBeforeFlip.firstTranscript.includes("Smoke clip 1")) {
      throw new Error(`expected newest page order before flip: ${clipControlsBeforeFlip.firstTranscript}`);
    }
    if (!clipControlsAfterFlip.firstTranscript.includes("Smoke clip 144")) {
      throw new Error(`expected oldest page order after flip: ${clipControlsAfterFlip.firstTranscript}`);
    }
    if (clipControlsAfterFlip.renderedClips !== 24) {
      throw new Error(`clip controls did not keep the fixed first batch: ${JSON.stringify(clipControlsAfterFlip)}`);
    }
    await page.goto(`${baseUrl}/operator/`);
    await page.locator("#clips .clip-card").first().waitFor({ state: "visible", timeout: 10000 });
    holdFeatureClipResponses = true;
    await page
      .locator("#clips .clip-card")
      .first()
      .getByRole("button", { name: "Add to Hall of Fame", exact: true })
      .click();
    await page.waitForFunction(() =>
      document
        .querySelector("#clips .clip-card:first-child .feature-clip-button")
        ?.classList.contains("is-saving"),
    );
    const operatorFeatureImmediateState = await page.evaluate(() => ({
      buttonText:
        document.querySelector("#clips .clip-card:first-child .feature-clip-button")?.textContent?.trim() || "",
      buttonLabel:
        document.querySelector("#clips .clip-card:first-child .feature-clip-button")?.getAttribute("aria-label") ||
        "",
      buttonPressed:
        document.querySelector("#clips .clip-card:first-child .feature-clip-button")?.getAttribute("aria-pressed") ||
        "",
      buttonSaving: document
        .querySelector("#clips .clip-card:first-child .feature-clip-button")
        ?.classList.contains("is-saving"),
      featuredPill: document.querySelector("#clips .clip-card:first-child .featured-pill")?.textContent || "",
      cardFeatured: document.querySelector("#clips .clip-card:first-child")?.classList.contains("is-featured"),
    }));
    if (
      operatorFeatureImmediateState.buttonText !== "★" ||
      operatorFeatureImmediateState.buttonLabel !== "Remove from Hall of Fame" ||
      operatorFeatureImmediateState.buttonPressed !== "true" ||
      !operatorFeatureImmediateState.buttonSaving ||
      operatorFeatureImmediateState.featuredPill !== "Featured" ||
      !operatorFeatureImmediateState.cardFeatured
    ) {
      throw new Error(`operator feature action did not update immediately: ${JSON.stringify(operatorFeatureImmediateState)}`);
    }
    holdFeatureClipResponses = false;
    releaseFeatureClipResponses.splice(0).forEach((release) => release());
    await page.waitForFunction(
      () =>
        document
          .querySelector("#clips .clip-card:first-child .feature-clip-button")
          ?.getAttribute("aria-pressed") === "true",
    );
    const operatorFeatureState = await page.evaluate(() => ({
      firstTranscript: document.querySelector("#clips .clip-card:first-child blockquote")?.textContent || "",
      buttonText:
        document.querySelector("#clips .clip-card:first-child .feature-clip-button")?.textContent?.trim() || "",
      buttonLabel:
        document.querySelector("#clips .clip-card:first-child .feature-clip-button")?.getAttribute("aria-label") ||
        "",
      featuredPill: document.querySelector("#clips .clip-card:first-child .featured-pill")?.textContent || "",
    }));
    if (
      !operatorFeatureState.firstTranscript.includes("Smoke clip 1") ||
      operatorFeatureState.buttonText !== "★" ||
      operatorFeatureState.buttonLabel !== "Remove from Hall of Fame" ||
      operatorFeatureState.featuredPill !== "Featured"
    ) {
      throw new Error(`operator feature action did not update the clip card: ${JSON.stringify(operatorFeatureState)}`);
    }
    await page.getByRole("tab", { name: "Performance" }).click();
    await page.locator(".system-kpi-panel .performance-card").first().waitFor({ state: "visible", timeout: 10000 });
    await page.getByRole("tab", { name: "About" }).click();
    const aboutState = await page.evaluate(() => ({
      pathname: window.location.pathname,
      hidden: document.querySelector("#panel-about")?.hidden ?? true,
      activeTab: document.querySelector(".tab.is-active")?.textContent?.trim() || "",
      creatorHref: document.querySelector("#panel-about .about-credit a")?.getAttribute("href") || "",
      creatorText: document.querySelector("#panel-about .about-credit a")?.textContent?.trim() || "",
      creatorRel: document.querySelector("#panel-about .about-credit a")?.getAttribute("rel") || "",
      bodyText: document.querySelector("#panel-about")?.textContent || "",
    }));
    if (
      aboutState.pathname !== "/about/" ||
      aboutState.hidden ||
      aboutState.activeTab !== "About" ||
      aboutState.creatorHref !== "https://robertboscacci.com/" ||
      aboutState.creatorText !== "Robert Boscacci" ||
      aboutState.creatorRel !== "noopener" ||
      !aboutState.bodyText.includes("Raspberry Pi radio edge") ||
      !aboutState.bodyText.includes("Ubuntu micro-computer") ||
      !aboutState.bodyText.includes("Whisper") ||
      !aboutState.bodyText.includes("large-v3-turbo") ||
      !aboutState.bodyText.includes("CTranslate2/faster-whisper")
    ) {
      throw new Error(`about tab did not expose the creator credit: ${JSON.stringify(aboutState)}`);
    }
    const desktopPerformanceContext = await browser.newContext({ viewport: { width: 1280, height: 900 } });
    let performanceHover = null;
    let defaultRangeState = null;
    let shortRangeState = null;
    let longRangeState = null;
    let searchDefaultState = null;
    try {
      const desktopPerformancePage = await desktopPerformanceContext.newPage();
      await desktopPerformancePage.goto(`${baseUrl}/search/`);
      searchDefaultState = await desktopPerformancePage.evaluate(() => ({
        activeRecency: document
          .querySelector("#clip-search-recency .clip-segment-button.is-active")
          ?.textContent?.trim() || "",
        activeLimit: document
          .querySelector("#clip-search-limit .clip-segment-button.is-active")
          ?.textContent?.trim() || "",
        pressedRecency: document
          .querySelector("#clip-search-recency .clip-segment-button[aria-pressed='true']")
          ?.textContent?.trim() || "",
        pressedLimit: document
          .querySelector("#clip-search-limit .clip-segment-button[aria-pressed='true']")
          ?.textContent?.trim() || "",
        selectorMetrics: Array.from(
          document.querySelectorAll("#clip-search-recency .clip-segmented-control, #clip-search-limit .clip-segmented-control"),
        ).map((control) => {
          const buttons = Array.from(control.querySelectorAll(".clip-segment-button"));
          const controlRect = control.getBoundingClientRect();
          const firstButton = buttons[0]?.getBoundingClientRect();
          const lastButton = buttons.at(-1)?.getBoundingClientRect();
          const buttonSpan = firstButton && lastButton ? lastButton.right - firstButton.left : 0;
          return {
            controlWidth: Math.round(controlRect.width),
            buttonSpan: Math.round(buttonSpan),
            extraSpace: Math.round(controlRect.width - buttonSpan),
          };
        }),
        suggestions: {
          hidden: document.querySelector("#clip-search-suggestions")?.hidden ?? true,
          groupCount: document.querySelectorAll(".search-suggestion-group").length,
          chipLabels: [...document.querySelectorAll(".search-suggestion-chip")].map((button) =>
            button.textContent?.trim(),
          ),
        },
      }));
      if (
        searchDefaultState.activeRecency !== "7d" ||
        searchDefaultState.activeLimit !== "10" ||
        searchDefaultState.pressedRecency !== "7d" ||
        searchDefaultState.pressedLimit !== "10"
      ) {
        throw new Error(`search defaults were not visibly selected: ${JSON.stringify(searchDefaultState)}`);
      }
      if (searchDefaultState.selectorMetrics.some((metric) => metric.extraSpace > 16)) {
        throw new Error(`search selectors have excessive empty space: ${JSON.stringify(searchDefaultState.selectorMetrics)}`);
      }
      if (
        searchDefaultState.suggestions.hidden ||
        searchDefaultState.suggestions.groupCount < 4 ||
        !searchDefaultState.suggestions.chipLabels.some((label) => label.toLowerCase().includes("tug barge"))
      ) {
        throw new Error(`search suggestions did not render before searching: ${JSON.stringify(searchDefaultState.suggestions)}`);
      }
      await desktopPerformancePage
        .locator("#clip-search-suggestions")
        .getByRole("button", { name: /tug barge/i })
        .click();
      await desktopPerformancePage.locator(".search-result-card").first().waitFor({ state: "visible", timeout: 10000 });
      const searchResult = await desktopPerformancePage.evaluate(() => ({
        query: document.querySelector("#clip-search-query")?.value || "",
        suggestionsHidden: document.querySelector("#clip-search-suggestions")?.hidden ?? false,
        status: document.querySelector("#clip-search-status")?.textContent || "",
        resultCount: document.querySelectorAll(".search-result-card").length,
        firstTranscript: document.querySelector(".search-result-card blockquote")?.textContent || "",
        audioCount: document.querySelectorAll(".search-result-card audio").length,
        playersPerResult: [...document.querySelectorAll(".search-result-card")].map(
          (card) => card.querySelectorAll(".example-player").length,
        ),
      }));
      if (searchResult.query !== "tug barge" || !searchResult.suggestionsHidden) {
        throw new Error(`search suggestion did not populate and hide suggestions: ${JSON.stringify(searchResult)}`);
      }
      if (!searchResult.status.includes("semantic matches") || searchResult.resultCount < 1) {
        throw new Error(`search results did not render: ${JSON.stringify(searchResult)}`);
      }
      if (!searchResult.firstTranscript.includes("Smoke search")) {
        throw new Error(`search result transcript did not come from search API: ${JSON.stringify(searchResult)}`);
      }
      if (
        searchResult.audioCount !== searchResult.resultCount ||
        searchResult.playersPerResult.some((count) => count !== 1)
      ) {
        throw new Error(`search results did not render exactly one audio player each: ${JSON.stringify(searchResult)}`);
      }
      await desktopPerformancePage
        .locator("#clip-search-recency")
        .getByRole("button", { name: "24h", exact: true })
        .click();
      await desktopPerformancePage.waitForFunction(
        () => document.querySelector("#clip-search-status")?.textContent?.includes("last 24h"),
        null,
        { timeout: 10000 },
      );
      const searchRecencyState = await desktopPerformancePage.evaluate(() => ({
        active: document.querySelector("#clip-search-recency .is-active")?.textContent?.trim() || "",
        pressed24h: [...document.querySelectorAll("#clip-search-recency button")]
          .find((button) => button.textContent?.trim() === "24h")
          ?.getAttribute("aria-pressed"),
      }));
      if (searchRecencyState.active !== "24h" || searchRecencyState.pressed24h !== "true") {
        throw new Error(`search recency selection did not update: ${JSON.stringify(searchRecencyState)}`);
      }
      await desktopPerformancePage.getByLabel("Search transcript meaning").fill("");
      await desktopPerformancePage.waitForFunction(
        () => document.querySelector("#clip-search-suggestions")?.hidden === false,
        null,
        { timeout: 10000 },
      );
      const clearedSearchState = await desktopPerformancePage.evaluate(() => ({
        status: document.querySelector("#clip-search-status")?.textContent || "",
        suggestionsHidden: document.querySelector("#clip-search-suggestions")?.hidden ?? true,
        resultText: document.querySelector("#clip-search-results")?.textContent || "",
      }));
      if (clearedSearchState.suggestionsHidden || !clearedSearchState.resultText.includes("Enter a search string")) {
        throw new Error(`clearing search did not restore suggestions: ${JSON.stringify(clearedSearchState)}`);
      }
      await desktopPerformancePage.getByRole("tab", { name: "Performance" }).click();
      const firstChart = desktopPerformancePage.locator(".performance-chart-svg").first();
      await firstChart.waitFor({ state: "visible", timeout: 10000 });
      defaultRangeState = await desktopPerformancePage.evaluate(() => {
        const firstSvg = document.querySelector(".performance-chart-svg");
        return {
          activeRange: document
            .querySelector(".performance-range-option[aria-pressed='true']")
            ?.textContent?.trim(),
          windowHours: firstSvg?.getAttribute("data-window-hours") || "",
          xTickLabels: [...document.querySelectorAll(".performance-chart:first-child .performance-chart-x-axis")].map(
            (tick) => tick.textContent || "",
          ),
        };
      });
      if (
        defaultRangeState.activeRange !== "2h" ||
        defaultRangeState.windowHours !== "2" ||
        defaultRangeState.xTickLabels.length < 4
      ) {
        throw new Error(`performance default time axis did not render: ${JSON.stringify(defaultRangeState)}`);
      }
      await desktopPerformancePage.getByRole("button", { name: "30m", exact: true }).click();
      shortRangeState = await desktopPerformancePage.evaluate(() => {
        const firstSvg = document.querySelector(".performance-chart-svg");
        return {
          activeRange: document
            .querySelector(".performance-range-option[aria-pressed='true']")
            ?.textContent?.trim(),
          windowHours: firstSvg?.getAttribute("data-window-hours") || "",
          xTickLabels: [...document.querySelectorAll(".performance-chart:first-child .performance-chart-x-axis")].map(
            (tick) => tick.textContent || "",
          ),
        };
      });
      await desktopPerformancePage.getByRole("button", { name: "3d", exact: true }).click();
      longRangeState = await desktopPerformancePage.evaluate(() => {
        const firstSvg = document.querySelector(".performance-chart-svg");
        return {
          activeRange: document
            .querySelector(".performance-range-option[aria-pressed='true']")
            ?.textContent?.trim(),
          windowHours: firstSvg?.getAttribute("data-window-hours") || "",
          xTickLabels: [...document.querySelectorAll(".performance-chart:first-child .performance-chart-x-axis")].map(
            (tick) => tick.textContent || "",
          ),
        };
      });
      if (
        shortRangeState.activeRange !== "30m" ||
        shortRangeState.windowHours !== "0.5" ||
        shortRangeState.xTickLabels.length < 4
      ) {
        throw new Error(`performance 30m time axis did not respond: ${JSON.stringify(shortRangeState)}`);
      }
      if (
        longRangeState.activeRange !== "3d" ||
        longRangeState.windowHours !== "72" ||
        longRangeState.xTickLabels.length < 4 ||
        longRangeState.xTickLabels.join("|") === shortRangeState.xTickLabels.join("|")
      ) {
        throw new Error(`performance 3d time axis did not respond: ${JSON.stringify(longRangeState)}`);
      }
      await firstChart.scrollIntoViewIfNeeded();
      const box = await firstChart.boundingBox();
      if (!box) {
        throw new Error("performance chart did not have a bounding box");
      }
      await desktopPerformancePage.mouse.move(box.x + box.width * 0.55, box.y + box.height * 0.45);
      await desktopPerformancePage.waitForTimeout(250);
      performanceHover = await desktopPerformancePage.evaluate(() => ({
        tooltip: document.querySelector(".performance-chart-tooltip:not([hidden])")?.textContent || "",
        tooltipCount: document.querySelectorAll(".performance-chart-tooltip").length,
        visibleTooltipCount: document.querySelectorAll(".performance-chart-tooltip:not([hidden])").length,
        chartCount: document.querySelectorAll(".performance-chart").length,
        lineCount: document.querySelectorAll(".performance-chart-line").length,
        hitAreaCount: document.querySelectorAll(".performance-chart-hit-area").length,
        hoverLine: Boolean(document.querySelector(".performance-chart-hover-line:not([hidden])")),
        hoverDot: Boolean(document.querySelector(".performance-chart-hover-dot:not([hidden])")),
        hostTitles: [...document.querySelectorAll(".performance-host h3")].map((heading) => heading.textContent || ""),
      }));
      if (!performanceHover.tooltip.includes("%") || !performanceHover.hoverLine || !performanceHover.hoverDot) {
        throw new Error(`performance hover tooltip did not render: ${JSON.stringify(performanceHover)}`);
      }
      if (!performanceHover.hostTitles.includes("Ubuntu Micro-Computer")) {
        throw new Error(`performance host labels were not updated: ${JSON.stringify(performanceHover)}`);
      }
    } finally {
      await desktopPerformanceContext.close();
    }
    const aisMapPage = await context.newPage();
    let aisMapState;
    try {
      await aisMapPage.goto(`${baseUrl}/ais/`);
      await aisMapPage.waitForTimeout(1000);
      aisMapState = await aisMapPage.evaluate(() => ({
        frameSrc: document.querySelector("#ais-catcher-frame")?.getAttribute("src") || "",
        frameHidden: document.querySelector("#ais-catcher-frame")?.hidden ?? null,
        unavailableHidden: document.querySelector("#ais-catcher-unavailable")?.hidden ?? null,
        status: document.querySelector("#map-status")?.textContent || "",
      }));
      aisMapState.shipRequests = aisShipRequests;
      aisMapState.viewerHeadRequests = aisViewerHeadRequests;
      if (
        !aisMapState.frameSrc.startsWith("/ais-catcher/") ||
        aisMapState.frameHidden ||
        !aisMapState.unavailableHidden ||
        !aisMapState.status.includes("Showing AIS-catcher live map") ||
        aisMapState.shipRequests < 1 ||
        aisMapState.viewerHeadRequests !== 0
      ) {
        throw new Error(`AIS map did not survive an upstream HEAD failure: ${JSON.stringify(aisMapState)}`);
      }
    } finally {
      await aisMapPage.close();
    }
    const continuousPlaybackContext = await browser.newContext({
      viewport: { width: 390, height: 844 },
      isMobile: true,
      hasTouch: true,
    });
    let continuousPlaybackState;
    try {
      const continuousPlaybackPage = await continuousPlaybackContext.newPage();
      await continuousPlaybackPage.route("**/api/clips/recent**", async (route) => {
        const payload = recentClipPayload(new URL(route.request().url()));
        payload.clips = payload.clips.slice(0, 2);
        payload.clip_count = 2;
        payload.filtered_clip_count = 2;
        payload.channel_counts = { "14": 2 };
        payload.next_cursor = null;
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify(payload),
        });
      });
      await continuousPlaybackPage.goto(`${baseUrl}/clips/`);
      await continuousPlaybackPage.waitForFunction(
        () => document.querySelectorAll("#clips .clip-card").length === 2,
        null,
        { timeout: 10000 },
      );
      const playAllButton = continuousPlaybackPage.getByRole("button", {
        name: "Play all recent clips",
        exact: true,
      });
      const firstAudio = continuousPlaybackPage.locator("#clips .clip-card:nth-child(1) audio");
      const secondAudio = continuousPlaybackPage.locator("#clips .clip-card:nth-child(2) audio");
      await playAllButton.click();
      await continuousPlaybackPage.waitForFunction(
        () => {
          const first = document.querySelector("#clips .clip-card:nth-child(1) audio");
          return (
            first instanceof HTMLAudioElement &&
            !first.paused &&
            Number.isFinite(first.duration) &&
            document
              .querySelector("#clips .clip-card:nth-child(1)")
              ?.classList.contains("is-continuous-playing")
          );
        },
        null,
        { timeout: 10000 },
      );
      await firstAudio.evaluate((audio) => {
        audio.currentTime = Math.max(0, audio.duration - 0.08);
      });
      await continuousPlaybackPage.waitForFunction(
        () =>
          document.querySelector(".clip-play-all-status")?.textContent ===
          "Next clip in 2 seconds",
        null,
        { timeout: 5000 },
      );
      const firstGapObservedAt = Date.now();
      await continuousPlaybackPage.waitForFunction(
        () => {
          const second = document.querySelector("#clips .clip-card:nth-child(2) audio");
          return second instanceof HTMLAudioElement && !second.paused;
        },
        null,
        { timeout: 5000 },
      );
      const observedGapMs = Date.now() - firstGapObservedAt;
      if (observedGapMs < 1700 || observedGapMs > 3500) {
        throw new Error(`continuous clip gap was not two seconds: ${observedGapMs}ms`);
      }
      await secondAudio.evaluate((audio) => {
        audio.currentTime = Math.max(0, audio.duration - 0.08);
      });
      await continuousPlaybackPage.waitForFunction(
        () =>
          document.querySelector(".clip-play-all-status")?.textContent ===
          "Next clip in 2 seconds",
        null,
        { timeout: 5000 },
      );
      await continuousPlaybackPage.waitForFunction(
        () => {
          const first = document.querySelector("#clips .clip-card:nth-child(1) audio");
          return first instanceof HTMLAudioElement && !first.paused;
        },
        null,
        { timeout: 5000 },
      );
      await continuousPlaybackPage.getByRole("button", {
        name: "Stop continuous clip playback",
        exact: true,
      }).click();
      continuousPlaybackState = await continuousPlaybackPage.evaluate(() => ({
        active:
          document.querySelector(".clip-play-all-button")?.getAttribute("aria-pressed") || "",
        buttonLabel:
          document.querySelector(".clip-play-all-button")?.getAttribute("aria-label") || "",
        status: document.querySelector(".clip-play-all-status")?.textContent || "",
        allPaused: [...document.querySelectorAll("#clips .clip-card audio")].every(
          (audio) => audio.paused,
        ),
      }));
      continuousPlaybackState.observedGapMs = observedGapMs;
      if (
        continuousPlaybackState.active !== "false" ||
        continuousPlaybackState.buttonLabel !== "Play all recent clips" ||
        !continuousPlaybackState.status.includes("2s between clips") ||
        !continuousPlaybackState.allPaused
      ) {
        throw new Error(
          `continuous clip playback did not loop and stop cleanly: ${JSON.stringify(continuousPlaybackState)}`,
        );
      }
    } finally {
      await continuousPlaybackContext.close();
    }
    console.log(
      JSON.stringify(
        {
          status: "ok",
          baseUrl,
          lazyClipShell,
          freshRefreshState,
          liveCatchupState,
          liveCatchupRaceState,
          liveQueueWaitState,
          liveSelectorState,
          liveManifestFallbackState,
          allButTrafficState,
          ...result,
          clipControls: {
            initialInfiniteScroll,
            infiniteScrollState,
            beforeFlip: clipControlsBeforeFlip,
            afterFlip: clipControlsAfterFlip,
          },
          aboutState,
          searchDefaultState,
          performanceHover,
          aisMapState,
          continuousPlaybackState,
          defaultRangeState,
          shortRangeState,
          longRangeState,
        },
        null,
        2,
      ),
    );
  } finally {
    await context.close();
    await browser.close();
  }
} finally {
  await close(server);
}

function recentClipPayload(url) {
  const liveQueueRequest = isLiveQueueRecentRequest(url);
  if (liveQueueRequest) {
    liveQueueRecentRequests += 1;
    if (returnEmptyLiveQueue) {
      return {
        clips: [],
        clip_count: 0,
        filtered_clip_count: 0,
        channel_counts: {},
        channel_labels: {},
        limit: 24,
        offset: 0,
        page: 1,
      };
    }
  }
  const limit = Math.min(Math.max(Number(url.searchParams.get("limit") || 6), 1), 100);
  const cursor = url.searchParams.get("cursor") || "";
  const cursorMatch = /^cursor-(\d+)$/.exec(cursor);
  const offset = cursorMatch ? Math.max(Number(cursorMatch[1]), 0) : 0;
  const page = Math.floor(offset / limit) + 1;
  const selectedChannels = url.searchParams.getAll("channels").map((channel) => channel.toUpperCase());
  const excludedChannels = new Set(
    url.searchParams
      .getAll("exclude_channels")
      .flatMap((channel) => channel.split(","))
      .map((channel) => channel.trim().toUpperCase())
      .filter(Boolean),
  );
  const total = 144;
  const featuredOnly = url.searchParams.get("featured") === "true";
  const oldestFirst = url.searchParams.get("sort") === "oldest";
  const around = url.searchParams.get("around") || "";
  const indexes = Array.from({ length: total }, (_value, index) => index).filter((index) => {
    if (featuredOnly && !featuredClipIndexes.has(index)) {
      return false;
    }
    return true;
  });
  if (oldestFirst) {
    indexes.reverse();
  }
  const filteredTotal = indexes.length;
  const defaultChannels = excludedChannels.has("14") ? ["05A"] : ["14"];
  const payloadChannels = (selectedChannels.length ? selectedChannels : defaultChannels).filter(
    (channel) => !excludedChannels.has(channel),
  );
  let clips = indexes
    .slice(offset, offset + limit)
    .map((index) =>
      recentClip(
        index,
        payloadChannels[index % payloadChannels.length] || "14",
        returnStaleLiveQueue && liveQueueRequest,
      ),
    );
  if (injectFreshRecentClip && !liveQueueRequest && offset === 0) {
    freshRecentClipSequence += 1;
    clips = [
      freshRecentClip(freshRecentClipSequence),
      ...clips.slice(0, Math.max(limit - 1, 0)),
    ];
  }
  if (returnStaleLiveQueue && liveQueueRequest) {
    servedStaleLiveQueue = true;
  }
  if (returnMixedAgeLiveQueue && liveQueueRequest) {
    servedMixedAgeLiveQueue = true;
    clips = [recentClip(0, "14", true), recentClip(0, "14"), recentClip(1, "14")];
  }
  if (
    injectLiveQueueRaceClip &&
    liveQueueRequest &&
    liveQueueRecentRequests > 1 &&
    !selectedChannels.length &&
    !excludedChannels.size
  ) {
    clips.unshift(liveQueueRaceClip(liveQueueRecentRequests));
  }
  return {
    clips,
    clip_count: total,
    filtered_clip_count: filteredTotal,
    featured: featuredOnly,
    channel_counts: Object.fromEntries(payloadChannels.map((channel) => [channel, filteredTotal])),
    channel_labels: Object.fromEntries(
      payloadChannels.map((channel) => [channel, channel === "14" ? "Vessel Traffic Service" : "Non-traffic"]),
    ),
    limit,
    offset,
    page,
    next_cursor:
      offset + clips.length < filteredTotal
        ? `cursor-${offset + clips.length}`
        : null,
    around: around ? "2026-08-15T19:30:00Z" : null,
    around_timezone: "America/Los_Angeles",
  };
}

function isLiveQueueRecentRequest(url) {
  return (
    url.searchParams.get("include_playback_url") === "true" &&
    url.searchParams.get("verify_playback_exists") === "false" &&
    url.searchParams.get("include_counts") === "false"
  );
}

function liveQueueRaceClip(sequence) {
  const startedAt = new Date(Date.now() + sequence * 1000).toISOString();
  return {
    id: `live-race-${sequence}`,
    channel: "16",
    channel_label: "Distress, Safety and Calling",
    started_at: startedAt,
    ended_at: new Date(Date.parse(startedAt) + 15000).toISOString(),
    duration_seconds: 15,
    transcript: `Live race clip ${sequence}`,
    transcript_public: `Live race clip ${sequence}`,
    playback_url: "",
  };
}

function freshRecentClip(sequence) {
  const startedAt = new Date(Date.now() + sequence * 1000).toISOString();
  return {
    id: `fresh-live-${sequence}`,
    channel: "14",
    channel_label: "Vessel Traffic Service",
    started_at: startedAt,
    ended_at: new Date(Date.parse(startedAt) + 15000).toISOString(),
    duration_seconds: 15,
    transcript: `Fresh live clip ${sequence}`,
    transcript_public: `Fresh live clip ${sequence}`,
    playback_url: "",
  };
}

function recentClip(index, channel = "14", stale = false) {
  const baseTime = stale ? Date.now() - 6 * 60 * 1000 : Date.parse(audioStartedAt);
  const startedAt = new Date(baseTime - index * 60000).toISOString();
  return {
    id: `clip-${index + 1}`,
    channel,
    channel_label: channel === "14" ? "Vessel Traffic Service" : "Non-traffic",
    started_at: startedAt,
    ended_at: new Date(Date.parse(startedAt) + 15000).toISOString(),
    duration_seconds: 15,
    transcript: `Smoke clip ${index + 1}`,
    transcript_public: `Smoke clip ${index + 1}`,
    featured: featuredClipIndexes.has(index),
    featured_at: featuredClipIndexes.has(index) ? "2026-06-01T12:00:00Z" : null,
    playback_url: "",
  };
}

function publishedManifestPayload() {
  const clips = Array.from({ length: 8 }, (_value, index) => {
    const clip = recentClip(index, index % 2 === 0 ? "14" : "13");
    return {
      ...clip,
      public_title: `Published ${clip.channel} ${index + 1}`,
      audio_public_filename: `published-${index + 1}.wav`,
    };
  });
  return {
    site: {
      title: "Elliott Bay VHF",
      subtitle: "Smoke manifest",
    },
    stats: {
      clip_count: clips.length,
      playable_clip_count: clips.length,
      channel_counts: { "13": 4, "14": 4 },
      playable_channel_counts: { "13": 4, "14": 4 },
      generated_at: "2026-06-01T18:30:00Z",
    },
    generated_at: "2026-06-01T18:30:00Z",
    clips,
  };
}

async function clipFeaturePayload(request) {
  const rawBody = await readRequestBody(request);
  const payload = JSON.parse(rawBody || "{}");
  const clipIndex = clipIndexForStartedAt(String(payload.started_at || ""));
  if (clipIndex < 0) {
    return {
      status: "unfeatured",
      channel: payload.channel || "14",
      started_at: payload.started_at || "",
      featured: false,
    };
  }
  const featured = Boolean(payload.featured);
  if (featured) {
    featuredClipIndexes.add(clipIndex);
  } else {
    featuredClipIndexes.delete(clipIndex);
  }
  return {
    status: featured ? "featured" : "unfeatured",
    channel: payload.channel || "14",
    started_at: new Date(Date.parse(audioStartedAt) - clipIndex * 60000).toISOString(),
    featured,
  };
}

function clipIndexForStartedAt(startedAt) {
  const parsedMs = Date.parse(startedAt);
  if (!Number.isFinite(parsedMs)) {
    return -1;
  }
  const baseMs = Date.parse(audioStartedAt);
  const index = Math.round((baseMs - parsedMs) / 60000);
  return index >= 0 ? index : -1;
}

function searchPayload(url) {
  const query = url.searchParams.get("q") || "";
  return {
    status: "ok",
    query,
    recency: url.searchParams.get("recency") || "7d",
    limit: Number(url.searchParams.get("limit") || 10),
    count: 2,
    index: {
      generated_at: "2026-06-01T18:30:00Z",
      source_clip_count: 72,
    },
    results: [
      {
        channel: "14",
        channel_label: "VTS / Seattle Traffic",
        started_at: audioStartedAt,
        ended_at: "2026-05-31T20:00:15Z",
        duration_seconds: 15,
        transcript: `Smoke search result for ${query}`,
        score: 0.93,
      },
      {
        channel: "13",
        channel_label: "Bridge-to-bridge",
        started_at: "2026-05-31T19:58:00Z",
        ended_at: "2026-05-31T19:58:10Z",
        duration_seconds: 10,
        transcript: "Smoke search bridge result",
        score: 0.81,
      },
    ],
  };
}

function performancePayload() {
  const generatedAt = "2026-06-01T18:30:00Z";
  const history = Array.from({ length: 3 }, (_value, index) => ({
    generatedAt: new Date(Date.parse(generatedAt) - (2 - index) * 60_000).toISOString(),
    cpuUtilizationPercent: 8 + index,
    memoryUsedPercent: 42 + index,
    thermalTemperatureC: 52 + index,
  }));
  return {
    generatedAt,
    hosts: [
      {
        role: "Ubuntu Micro-Computer",
        cpuCount: 8,
        cpuUtilizationPercent: 10,
        memoryUsedPercent: 44,
        thermalTemperatureC: 54,
        disks: [{ mountpoint: "/", usedPercent: 61 }],
        cpu: { status: "ok" },
        memory: { status: "ok" },
        thermal: { status: "ok" },
        history,
      },
    ],
  };
}

function liveChannelsPayload() {
  const channels = [
    ["13", "Bridge-to-bridge", "156.650"],
    ["14", "VTS / Seattle Traffic", "156.700"],
    ["66A", "Port Operations", "156.325"],
    ["67", "Commercial / Bridge", "156.375"],
    ["68", "Recreational", "156.425"],
    ["69", "Non-commercial", "156.475"],
    ["71", "Non-commercial", "156.575"],
    ["72", "Ship-to-ship", "156.625"],
    ["73", "Port Operations", "156.675"],
    ["74", "Port Operations", "156.725"],
    ["77", "Ship-to-ship", "156.875"],
    ["78A", "Non-commercial", "156.925"],
  ];
  return {
    defaultChannel: "14",
    channels: channels.map(([channel, label, frequencyMhz]) => ({
      channel,
      label,
      frequencyMhz,
      streamPath: `/api/live/${channel}/current.mp3`,
      statusPath: `/api/live/${channel}/status`,
    })),
  };
}

function lexicalPayload() {
  return {
    status: "ok",
    generated_at: "2026-05-31T20:01:00Z",
    source_clip_count: 46668,
    channels: { "06": 8, "14": 2 },
    frequency: {
      by_channel: { "06": 8, "14": 2 },
      by_hour_pacific: { "13:00": 2 },
      by_day_pacific: { "2026-05-31": 2 },
    },
    terms: {
      semantic_buckets: {
        communication_markers: [{ term: "roger", count: 16 }],
        movement: [{ term: "southbound", count: 8 }],
        places: [{ term: "west waterway", count: 5 }],
        vessel_types: [],
      },
      bigrams: [{ term: "tug barge", count: 7 }],
    },
    entities: [
      {
        name: "Seattle Traffic",
        kind: "shore_station",
        count: 2,
        confidence: 0.99,
        channels: { "14": 2 },
        examples: [
          {
            channel: "14",
            started_at: audioStartedAt,
            duration_seconds: 0.25,
            text: "Seattle traffic smoke test.",
          },
        ],
      },
      {
        name: "Tacoma Traffic",
        kind: "shore_station",
        count: 1,
        confidence: 0.9,
        channels: { "14": 1 },
        examples: [],
      },
    ],
    topics: {
      status: "ok",
      plot_url: "/analysis/topic_clusters.html",
      items: [
        {
          id: 0,
          label: "Seattle Traffic / pilots",
          count: 2,
          top_words: ["Seattle Traffic"],
          examples: [
            {
              channel: "14",
              started_at: "2026-05-31T19:59:00Z",
              duration_seconds: 0.25,
              text: "Seattle Traffic topic smoke example.",
            },
          ],
        },
      ],
    },
    education_guide: [],
    education: [],
  };
}

async function sendStatic(response, pathname) {
  let relativePath = decodeURIComponent(pathname);
  if (
    relativePath === "/" ||
    relativePath === "/clips/" ||
    relativePath === "/clips" ||
    relativePath === "/search/" ||
    relativePath === "/search" ||
    relativePath === "/operator/" ||
    relativePath === "/operator" ||
    relativePath === "/performance/" ||
    relativePath === "/performance" ||
    relativePath === "/ais/" ||
    relativePath === "/ais" ||
    relativePath === "/analysis/" ||
    relativePath === "/analysis" ||
    relativePath === "/about/" ||
    relativePath === "/about"
  ) {
    relativePath = "/index.html";
  }
  const safePath = normalize(relativePath).replace(/^(\.\.[/\\])+/, "");
  const absolutePath = join(publicSiteRoot, safePath);
  if (!absolutePath.startsWith(publicSiteRoot)) {
    response.writeHead(404);
    response.end();
    return;
  }
  try {
    const body = await readFile(absolutePath);
    response.writeHead(200, {
      "content-type": mimeTypes[extname(absolutePath)] || "application/octet-stream",
      "cache-control": "no-store",
    });
    response.end(body);
  } catch {
    response.writeHead(404);
    response.end();
  }
}

function sendJson(response, payload, status = 200) {
  response.writeHead(status, {
    "content-type": "application/json; charset=utf-8",
    "cache-control": "no-store",
  });
  response.end(JSON.stringify(payload));
}

async function readRequestBody(request) {
  const chunks = [];
  for await (const chunk of request) {
    chunks.push(Buffer.from(chunk));
  }
  return Buffer.concat(chunks).toString("utf8");
}

function sendHtml(response, body) {
  response.writeHead(200, {
    "content-type": "text/html; charset=utf-8",
    "cache-control": "no-store",
  });
  response.end(body);
}

function sendBytes(response, body, contentType) {
  response.writeHead(200, {
    "content-type": contentType,
    "cache-control": "no-store",
    "content-length": body.length,
  });
  response.end(body);
}

function wavSilence({ sampleRate = 8000, durationSeconds = 0.25 } = {}) {
  const sampleCount = Math.floor(sampleRate * durationSeconds);
  const dataSize = sampleCount * 2;
  const buffer = Buffer.alloc(44 + dataSize);
  buffer.write("RIFF", 0);
  buffer.writeUInt32LE(36 + dataSize, 4);
  buffer.write("WAVE", 8);
  buffer.write("fmt ", 12);
  buffer.writeUInt32LE(16, 16);
  buffer.writeUInt16LE(1, 20);
  buffer.writeUInt16LE(1, 22);
  buffer.writeUInt32LE(sampleRate, 24);
  buffer.writeUInt32LE(sampleRate * 2, 28);
  buffer.writeUInt16LE(2, 32);
  buffer.writeUInt16LE(16, 34);
  buffer.write("data", 36);
  buffer.writeUInt32LE(dataSize, 40);
  return buffer;
}

function wavTestSignal({ sampleRate = 8000, durationSeconds = 3 } = {}) {
  const buffer = wavSilence({ sampleRate, durationSeconds });
  const sampleCount = Math.floor(sampleRate * durationSeconds);
  for (let index = 0; index < sampleCount; index += 1) {
    const time = index / sampleRate;
    const envelope = 0.12 + 0.78 * Math.abs(Math.sin(Math.PI * 1.7 * time));
    const carrier = Math.sin(2 * Math.PI * 620 * time);
    const sample = Math.round(32767 * 0.42 * envelope * carrier);
    buffer.writeInt16LE(sample, 44 + index * 2);
  }
  return buffer;
}

function listen(serverToListen) {
  return new Promise((resolve, reject) => {
    serverToListen.once("error", reject);
    serverToListen.listen(0, "127.0.0.1", () => {
      serverToListen.off("error", reject);
      resolve(serverToListen.address());
    });
  });
}

function close(serverToClose) {
  return new Promise((resolve, reject) => {
    serverToClose.close((error) => (error ? reject(error) : resolve()));
  });
}
