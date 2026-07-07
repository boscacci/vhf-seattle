#!/usr/bin/env node
import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import { extname, join, normalize } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const repoRoot = fileURLToPath(new URL("..", import.meta.url));
const publicSiteRoot = join(repoRoot, "public-site");
const audioStartedAt = "2026-05-31T20:00:00Z";
let holdRecentClipResponses = false;
let releaseRecentClipResponses = [];
let holdFeatureClipResponses = false;
let releaseFeatureClipResponses = [];
let topicClusterReturnsNotFound = false;
const recentClipRequestUrls = [];
const featuredClipIndexes = new Set([1, 7, 13, 49, 91]);
const reviewedClipIndexes = new Set([0, 2, 5, 8, 21, 34]);
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
      return sendBytes(response, wavSilence(), "audio/wav");
    }
    if (url.pathname === "/api/clips/recent") {
      recentClipRequestUrls.push(new URL(url.href));
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
    if (url.pathname === "/api/clips/corrections" && request.method === "POST") {
      if (request.headers["x-talkingboats-tailnet-dev"] !== "1") {
        return sendJson(response, { detail: "tailnet operator access required" }, 403);
      }
      return sendJson(response, await transcriptCorrectionPayload(request));
    }
    if (url.pathname === "/api/clips/corrections" && request.method === "DELETE") {
      if (request.headers["x-talkingboats-tailnet-dev"] !== "1") {
        return sendJson(response, { detail: "tailnet operator access required" }, 403);
      }
      return sendJson(response, await transcriptCorrectionDeletePayload(request));
    }
    if (url.pathname === "/api/clips/search") {
      return sendJson(response, searchPayload(url));
    }
    if (url.pathname === "/api/asr-feedback/status") {
      if (request.headers["x-talkingboats-tailnet-dev"] !== "1") {
        return sendJson(response, { detail: "tailnet operator access required" }, 403);
      }
      return sendJson(response, asrFeedbackStatusPayload());
    }
    if (url.pathname === "/api/live/performance") {
      return sendJson(response, performancePayload());
    }
    if (url.pathname === "/api/live/channels") {
      return sendJson(response, { channels: [] });
    }
    if (url.pathname === "/analysis/topic_clusters.html") {
      if (topicClusterReturnsNotFound) {
        return sendJson(response, { detail: "asset not found" }, 404);
      }
      return sendHtml(response, "<html><body>topic clusters</body></html>");
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
    await page.locator("#clips .clip-placeholder").first().waitFor({ state: "visible", timeout: 10000 });
    const lazyClipShell = await page.evaluate(() => ({
      busy: document.querySelector("#clips")?.getAttribute("aria-busy"),
      placeholderCount: document.querySelectorAll("#clips .clip-placeholder").length,
      controlsText: document.querySelector("#clip-display-controls")?.textContent || "",
      status: document.querySelector("#clip-status")?.textContent || "",
    }));
    if (lazyClipShell.busy !== "true") {
      throw new Error(`recent clip list did not mark itself busy while lazy-loading: ${JSON.stringify(lazyClipShell)}`);
    }
    if (lazyClipShell.placeholderCount < 3) {
      throw new Error(`recent clip lazy placeholders did not render: ${JSON.stringify(lazyClipShell)}`);
    }
    if (
      !lazyClipShell.controlsText.includes("Clips per page") ||
      !lazyClipShell.controlsText.includes("24") ||
      lazyClipShell.controlsText.includes("48")
    ) {
      throw new Error(`recent clip controls were not available during lazy load: ${JSON.stringify(lazyClipShell)}`);
    }
    if (!lazyClipShell.status.includes("Loading recent clips")) {
      throw new Error(`recent clip lazy status was not clear: ${JSON.stringify(lazyClipShell)}`);
    }
    holdRecentClipResponses = false;
    releaseRecentClipResponses.splice(0).forEach((release) => release());
    await page.locator("#clips .clip-card").first().waitFor({ state: "visible", timeout: 10000 });
    const labelingLink = await page.evaluate(() => {
      const link = document.querySelector("#operator-labeling-link");
      if (!(link instanceof HTMLAnchorElement)) {
        throw new Error("operator labeling link did not render");
      }
      return {
        hidden: link.hidden,
        text: link.textContent?.trim() || "",
        href: link.getAttribute("href") || "",
      };
    });
    if (labelingLink.hidden || labelingLink.text !== "Label clips" || labelingLink.href !== "/operator/") {
      throw new Error(`dev clip review labeling link is not reachable: ${JSON.stringify(labelingLink)}`);
    }
    const devClipFeatureState = await page.evaluate(() => ({
      firstTranscript: document.querySelector("#clips .clip-card:first-child blockquote")?.textContent || "",
      buttonText:
        document.querySelector("#clips .clip-card:first-child .feature-clip-button")?.textContent?.trim() || "",
      buttonLabel:
        document.querySelector("#clips .clip-card:first-child .feature-clip-button")?.getAttribute("aria-label") || "",
      buttonPressed:
        document.querySelector("#clips .clip-card:first-child .feature-clip-button")?.getAttribute("aria-pressed") ||
        "",
      correctionOpen: Boolean(document.querySelector("#clips .clip-card:first-child .transcript-correction")),
    }));
    if (
      !devClipFeatureState.firstTranscript.includes("Smoke clip 1") ||
      devClipFeatureState.buttonText !== "☆" ||
      devClipFeatureState.buttonLabel !== "Add to Hall of Fame" ||
      devClipFeatureState.buttonPressed !== "false" ||
      devClipFeatureState.correctionOpen
    ) {
      throw new Error(`dev clip review star action is not visible without transcript editing: ${JSON.stringify(devClipFeatureState)}`);
    }
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
    await page.getByRole("tab", { name: "Live Monitor" }).click();
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
    await page.locator("#panel-live").getByRole("button", { name: "Pause" }).click();
    await page.locator("#live-primary-channel-picker").getByRole("button", { name: "All but Traffic" }).click();
    await page.locator("#panel-live").getByRole("button", { name: "Play" }).click();
    await page.waitForFunction(() => {
      const queueText = document.querySelector("#live-queue")?.textContent || "";
      const src = document.querySelector("#live-audio")?.getAttribute("src") || "";
      return queueText.includes("Seattle Traffic is filtered out") && src.includes("/api/clips/audio?channel=");
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
    await page.locator("#panel-live").getByRole("button", { name: "Pause" }).click();
    await page.getByRole("tab", { name: "Clip Review" }).click();
    await page.getByRole("link", { name: "Label clips" }).click();
    await page.waitForURL(`${baseUrl}/operator/`, { timeout: 10000 });
    await page.locator("#clips .transcript-correction").first().waitFor({ state: "visible", timeout: 10000 });
    await page.goto(`${baseUrl}/analysis/`);
    await page.locator("#lexical-analysis audio").waitFor({ state: "visible", timeout: 10000 });
    const result = await page.evaluate(async () => {
      const cards = [...document.querySelectorAll(".language-card")];
      const activeCard = cards.find((card) => card.textContent?.includes("Analyzed channels"));
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
        audioCount: document.querySelectorAll("#lexical-analysis audio").length,
        correctionCount: document.querySelectorAll("#lexical-analysis .analysis-correction").length,
        panelHeadings: [...document.querySelectorAll("#lexical-analysis .language-panel h3")].map(
          (heading) => heading.textContent || "",
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
          correctionCount: topicPanel.querySelectorAll(".analysis-correction").length,
          hasRemovedSummary: Boolean(topicPanel.querySelector(".mobile-nlp-panel, .nlp-summary-grid")),
          bodyText: topicPanel.textContent || "",
        },
        metadata,
      };
    });
    if (result.activeChannelMetric !== "1 channel") {
      throw new Error(`expected active channel metric 1 channel, saw ${result.activeChannelMetric}`);
    }
    if (!String(result.metadata.src).includes("/api/clips/audio?channel=14&started_at=")) {
      throw new Error(`analysis audio did not use same-origin clip API: ${result.metadata.src}`);
    }
    if (result.correctionCount < 2 || result.transcriptTopics.correctionCount < 1) {
      throw new Error(`analysis route should expose correction controls for ASR tuning: ${JSON.stringify(result)}`);
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
    await page.locator("#lexical-analysis .entity-card:first-child .analysis-correction summary").click();
    await page
      .locator("#lexical-analysis .entity-card:first-child .analysis-correction .transcript-correction-label textarea")
      .fill("Direct analysis page correction for ASR tuning.");
    await page.locator("#lexical-analysis .entity-card:first-child .analysis-correction button[type='submit']").click();
    await page.waitForFunction(() =>
      document
        .querySelector("#lexical-analysis .entity-card:first-child blockquote")
        ?.textContent?.includes("Direct analysis page correction"),
    );
    const directAnalysisCorrection = await page.evaluate(() => ({
      summary:
        document
          .querySelector("#lexical-analysis .entity-card:first-child .analysis-correction summary")
          ?.textContent?.trim() || "",
      status:
        document
          .querySelector("#lexical-analysis .entity-card:first-child .analysis-correction .transcript-correction-status")
          ?.textContent?.trim() || "",
      quote: document.querySelector("#lexical-analysis .entity-card:first-child blockquote")?.textContent || "",
    }));
    if (
      directAnalysisCorrection.summary !== "Edit correction" ||
      !directAnalysisCorrection.status.includes("Saved for manual fine tuning") ||
      !directAnalysisCorrection.quote.includes("Direct analysis page correction")
    ) {
      throw new Error(`direct analysis correction did not save: ${JSON.stringify(directAnalysisCorrection)}`);
    }
    topicClusterReturnsNotFound = true;
    const desktopContext = await browser.newContext({ viewport: { width: 1280, height: 900 } });
    try {
      const desktopPage = await desktopContext.newPage();
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
    await page.getByRole("tab", { name: "Clip Review" }).click();
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
    const initialPagination = await page.evaluate(() => {
      const pagination = document.querySelector("#clip-pagination");
      if (!(pagination instanceof HTMLElement)) {
        throw new Error("clip pagination did not render");
      }
      return {
        text: pagination.textContent || "",
        buttons: [...pagination.querySelectorAll("button")].map((button) => ({
          text: button.textContent?.trim() || "",
          current: button.getAttribute("aria-current"),
          disabled: button.disabled,
        })),
        actionButtons: [...pagination.querySelectorAll(".pagination-actions button")].map((button) => ({
          text: button.textContent?.trim() || "",
          disabled: button.disabled,
        })),
        ellipsisCount: pagination.querySelectorAll(".pagination-ellipsis").length,
      };
    });
    if (initialPagination.actionButtons.map((button) => button.text).join(",") !== "Next,Oldest") {
      throw new Error(`first page pagination should hide unusable previous actions: ${JSON.stringify(initialPagination)}`);
    }
    if (initialPagination.actionButtons.some((button) => button.disabled)) {
      throw new Error(`visible first page pagination actions should be usable: ${JSON.stringify(initialPagination)}`);
    }
    if (!initialPagination.buttons.some((button) => button.text === "1" && button.current === "page")) {
      throw new Error(`pagination current page button missing: ${JSON.stringify(initialPagination)}`);
    }
    if (initialPagination.buttons.some((button) => button.text === "24")) {
      throw new Error(`pagination kept a redundant last-page anchor: ${JSON.stringify(initialPagination)}`);
    }
    if (initialPagination.ellipsisCount < 1) {
      throw new Error(`pagination ellipsis missing: ${JSON.stringify(initialPagination)}`);
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
    await page.locator("#clip-display-controls").getByRole("button", { name: "Reviewed", exact: true }).click();
    await page.waitForFunction(() => document.querySelector("#clips blockquote")?.textContent?.includes("Smoke clip 1 reviewed"));
    const reviewedClipState = await page.evaluate(() => ({
      firstTranscript: document.querySelector("#clips blockquote")?.textContent || "",
      renderedClips: document.querySelectorAll("#clips .clip-card").length,
      status: document.querySelector("#clip-status")?.textContent || "",
      reviewedPills: document.querySelectorAll("#clips .reviewed-pill").length,
      activeShowMode: document
        .querySelector("#clip-display-controls .clip-control-group:first-child button[aria-pressed='true']")
        ?.textContent?.trim(),
    }));
    if (
      reviewedClipState.activeShowMode !== "Reviewed" ||
      reviewedClipState.renderedClips !== reviewedClipIndexes.size ||
      reviewedClipState.reviewedPills !== reviewedClipIndexes.size ||
      !reviewedClipState.status.includes("reviewed") ||
      !reviewedClipState.firstTranscript.includes("Smoke clip 1 reviewed")
    ) {
      throw new Error(`reviewed filter did not show only reviewed clips: ${JSON.stringify(reviewedClipState)}`);
    }
    await page.locator("#clip-display-controls").getByRole("button", { name: "Recent", exact: true }).click();
    await page.waitForFunction(() => document.querySelector("#clips blockquote")?.textContent?.includes("Smoke clip 1"));
    await page.locator("#clip-pagination").getByRole("button", { name: "Page 2", exact: true }).click();
    await page.waitForFunction(() => document.querySelector("#clips blockquote")?.textContent?.includes("Smoke clip 7"));
    const secondPagePagination = await page.evaluate(() => ({
      firstTranscript: document.querySelector("#clips blockquote")?.textContent || "",
      activePage: document.querySelector("#clip-pagination button[aria-current='page']")?.textContent?.trim() || "",
    }));
    if (secondPagePagination.activePage !== "2") {
      throw new Error(`pagination did not mark page 2 active: ${JSON.stringify(secondPagePagination)}`);
    }
    await page.locator("#clip-pagination").getByRole("button", { name: "Page 5", exact: true }).click();
    await page.waitForFunction(() => document.querySelector("#clips blockquote")?.textContent?.includes("Smoke clip 25"));
    await page.locator("#clip-pagination").getByRole("button", { name: "Page 6", exact: true }).click();
    await page.waitForFunction(() => document.querySelector("#clips blockquote")?.textContent?.includes("Smoke clip 31"));
    const middlePagination = await page.evaluate(() => {
      const pagination = document.querySelector("#clip-pagination");
      const numberedButtons = [...pagination.querySelectorAll(".pagination-page-button")].map((button) =>
        button.textContent?.trim(),
      );
      return {
        text: pagination.textContent || "",
        numberedButtons,
        ellipsisCount: pagination.querySelectorAll(".pagination-ellipsis").length,
        activePage: pagination.querySelector("button[aria-current='page']")?.textContent?.trim() || "",
      };
    });
    if (middlePagination.activePage !== "6") {
      throw new Error(`pagination did not mark middle page active: ${JSON.stringify(middlePagination)}`);
    }
    if (middlePagination.numberedButtons.join(",") !== "4,5,6,7,8") {
      throw new Error(`pagination did not show five centered page numbers: ${JSON.stringify(middlePagination)}`);
    }
    if (middlePagination.ellipsisCount !== 2) {
      throw new Error(`pagination middle window should be bracketed by ellipses: ${JSON.stringify(middlePagination)}`);
    }
    holdRecentClipResponses = true;
    await page.locator("#clip-pagination").getByRole("button", { name: "Page 7", exact: true }).click();
    const pendingPagination = await page.evaluate(() => ({
      activePage: document.querySelector("#clip-pagination button[aria-current='page']")?.textContent?.trim() || "",
      busy: document.querySelector("#clip-pagination")?.getAttribute("aria-busy") || "",
      status: document.querySelector("#clip-status")?.textContent || "",
      firstTranscript: document.querySelector("#clips blockquote")?.textContent || "",
      loadingBanner: document.querySelector("#clips .clip-page-loading-banner")?.textContent || "",
    }));
    if (
      pendingPagination.activePage !== "7" ||
      pendingPagination.busy !== "true" ||
      !pendingPagination.status.includes("Loading page 7") ||
      !pendingPagination.loadingBanner.includes("Loading page 7")
    ) {
      throw new Error(`pagination did not provide immediate pending feedback: ${JSON.stringify(pendingPagination)}`);
    }
    if (!pendingPagination.firstTranscript.includes("Smoke clip 31")) {
      throw new Error(`pagination pending state should not flicker away the current cards: ${JSON.stringify(pendingPagination)}`);
    }
    holdRecentClipResponses = false;
    releaseRecentClipResponses.splice(0).forEach((release) => release());
    await page.waitForFunction(() => document.querySelector("#clips blockquote")?.textContent?.includes("Smoke clip 37"));
    const pageSevenRequest = [...recentClipRequestUrls].reverse().find(
      (requestUrl) =>
        requestUrl.searchParams.get("page") === "7" &&
        !requestUrl.searchParams.has("offset"),
    );
    if (!pageSevenRequest) {
      throw new Error("pagination numbered jump did not use page=7");
    }
    await page.locator("#clip-pagination").getByRole("button", { name: "Newest page" }).click();
    await page.waitForFunction(() => document.querySelector("#clips blockquote")?.textContent?.includes("Smoke clip 1"));
    await page.locator("#clip-pagination").getByRole("button", { name: "Oldest page" }).click();
    await page.waitForFunction(() => document.querySelector("#clips blockquote")?.textContent?.includes("Smoke clip 144"));
    const oldestPagePagination = await page.evaluate(() => ({
      firstTranscript: document.querySelector("#clips blockquote")?.textContent || "",
      activePage: document.querySelector("#clip-pagination button[aria-current='page']")?.textContent?.trim() || "",
      text: document.querySelector("#clip-pagination")?.textContent || "",
      activeSort: document
        .querySelector("#clip-display-controls .clip-control-group:last-child button[aria-pressed='true']")
        ?.textContent?.trim() || "",
      numberedButtons: [...document.querySelectorAll("#clip-pagination .pagination-page-button")].map((button) =>
        button.textContent?.trim(),
      ),
      actionButtons: [...document.querySelectorAll("#clip-pagination .pagination-actions button")].map((button) => ({
        text: button.textContent?.trim() || "",
        disabled: button.disabled,
      })),
    }));
    const oldestPageRequest = [...recentClipRequestUrls].reverse().find(
      (requestUrl) =>
        requestUrl.searchParams.get("sort") === "oldest" &&
        requestUrl.searchParams.get("page") === "1" &&
        !requestUrl.searchParams.has("offset"),
    );
    if (!oldestPageRequest) {
      throw new Error("pagination oldest jump did not use oldest-first page one");
    }
    if (oldestPagePagination.activePage !== "1" || oldestPagePagination.activeSort !== "Oldest") {
      throw new Error(`pagination oldest jump did not switch to oldest-first page one: ${JSON.stringify(oldestPagePagination)}`);
    }
    if (oldestPagePagination.numberedButtons.join(",") !== "1,2,3,4,5") {
      throw new Error(`pagination oldest window should show the oldest-first start: ${JSON.stringify(oldestPagePagination)}`);
    }
    if (oldestPagePagination.actionButtons.map((button) => button.text).join(",") !== "Next,Newest") {
      throw new Error(`oldest page pagination should expose newer navigation: ${JSON.stringify(oldestPagePagination)}`);
    }
    if (oldestPagePagination.actionButtons.some((button) => button.disabled)) {
      throw new Error(`visible oldest page pagination actions should be usable: ${JSON.stringify(oldestPagePagination)}`);
    }
    await page.locator("#clip-pagination").getByRole("button", { name: "Newest page" }).click();
    await page.waitForFunction(() => document.querySelector("#clips blockquote")?.textContent?.includes("Smoke clip 1"));
    await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
    const mobilePaginationScrollBeforeNext = await page.evaluate(() => ({
      scrollY: window.scrollY,
      clipsTop: document.querySelector("#clips")?.getBoundingClientRect().top ?? null,
    }));
    holdRecentClipResponses = true;
    await page.locator("#clip-pagination").getByRole("button", { name: "Next", exact: true }).click();
    const mobilePaginationPendingNext = await page.evaluate(
      (scrollBeforeNext) => ({
        activePage: document.querySelector("#clip-pagination button[aria-current='page']")?.textContent?.trim() || "",
        busy: document.querySelector("#clip-pagination")?.getAttribute("aria-busy") || "",
        status: document.querySelector("#clip-status")?.textContent || "",
        firstTranscript: document.querySelector("#clips blockquote")?.textContent || "",
        scrollY: window.scrollY,
        scrollYBeforeNext: scrollBeforeNext.scrollY,
        clipsTop: document.querySelector("#clips")?.getBoundingClientRect().top ?? null,
      }),
      mobilePaginationScrollBeforeNext,
    );
    if (
      mobilePaginationPendingNext.activePage !== "2" ||
      mobilePaginationPendingNext.busy !== "true" ||
      !mobilePaginationPendingNext.status.includes("Loading page 2") ||
      !mobilePaginationPendingNext.firstTranscript.includes("Smoke clip 1") ||
      mobilePaginationPendingNext.scrollY < mobilePaginationPendingNext.scrollYBeforeNext - 96 ||
      mobilePaginationPendingNext.clipsTop > 96
    ) {
      throw new Error(`mobile next-page pending state should stay near the clicked pagination: ${JSON.stringify(mobilePaginationPendingNext)}`);
    }
    holdRecentClipResponses = false;
    releaseRecentClipResponses.splice(0).forEach((release) => release());
    await page.waitForFunction(() => document.querySelector("#clips blockquote")?.textContent?.includes("Smoke clip 7"));
    await page.waitForFunction(() => {
      const clips = document.querySelector("#clips");
      const tabs = document.querySelector(".tabs");
      const tabsHeight = tabs instanceof HTMLElement ? tabs.getBoundingClientRect().height : 0;
      const clipsTop = clips instanceof HTMLElement ? clips.getBoundingClientRect().top : Number.NaN;
      const minTop = tabsHeight > 0 ? tabsHeight - 4 : -1;
      const maxTop = tabsHeight > 0 ? tabsHeight + 24 : 96;
      return clipsTop >= minTop && clipsTop <= maxTop;
    });
    const sixClipPageTwo = await page.evaluate(
      (scrollBeforeNext) => ({
        firstTranscript: document.querySelector("#clips blockquote")?.textContent || "",
        renderedClips: document.querySelectorAll("#clips .clip-card").length,
        pageStatus: document.querySelector("#clip-pagination")?.textContent || "",
        activePage: document.querySelector("#clip-pagination button[aria-current='page']")?.textContent?.trim() || "",
        clipsTop: document.querySelector("#clips")?.getBoundingClientRect().top ?? null,
        stickyTabsHeight: document.querySelector(".tabs")?.getBoundingClientRect().height ?? null,
      }),
      mobilePaginationScrollBeforeNext,
    );
    if (
      sixClipPageTwo.renderedClips !== 6 ||
      sixClipPageTwo.activePage !== "2" ||
      !sixClipPageTwo.firstTranscript.includes("Smoke clip 7")
    ) {
      throw new Error(`6-per-page second page did not establish the anchor: ${JSON.stringify(sixClipPageTwo)}`);
    }
    const minClipsTop = sixClipPageTwo.stickyTabsHeight ? sixClipPageTwo.stickyTabsHeight - 4 : -1;
    const maxClipsTop = sixClipPageTwo.stickyTabsHeight ? sixClipPageTwo.stickyTabsHeight + 24 : 96;
    if (
      sixClipPageTwo.clipsTop < minClipsTop ||
      sixClipPageTwo.clipsTop > maxClipsTop
    ) {
      throw new Error(`mobile next-page action did not scroll after the new clips rendered: ${JSON.stringify(sixClipPageTwo)}`);
    }
    let desktopPaginationState = null;
    const desktopPaginationContext = await browser.newContext({ viewport: { width: 1280, height: 900 } });
    try {
      const desktopPaginationPage = await desktopPaginationContext.newPage();
      await desktopPaginationPage.goto(`${baseUrl}/clips/`);
      await desktopPaginationPage.locator("#clips .clip-card").first().waitFor({ state: "visible", timeout: 10000 });
      await desktopPaginationPage.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
      const desktopPaginationBeforeNext = await desktopPaginationPage.evaluate(() => ({
        scrollY: window.scrollY,
        clipsTop: document.querySelector("#clips")?.getBoundingClientRect().top ?? null,
      }));
      holdRecentClipResponses = true;
      await desktopPaginationPage.locator("#clip-pagination").getByRole("button", { name: "Next", exact: true }).click();
      const desktopPaginationPending = await desktopPaginationPage.evaluate(
        (scrollBeforeNext) => ({
          activePage: document.querySelector("#clip-pagination button[aria-current='page']")?.textContent?.trim() || "",
          loadingBanner: document.querySelector("#clips .clip-page-loading-banner")?.textContent || "",
          busy: document.querySelector("#clip-pagination")?.getAttribute("aria-busy") || "",
          status: document.querySelector("#clip-status")?.textContent || "",
          firstTranscript: document.querySelector("#clips blockquote")?.textContent || "",
          clipsTop: document.querySelector("#clips")?.getBoundingClientRect().top ?? null,
          scrollY: window.scrollY,
          scrollYBeforeNext: scrollBeforeNext.scrollY,
          clipsTopBeforeNext: scrollBeforeNext.clipsTop,
        }),
        desktopPaginationBeforeNext,
      );
      if (
        desktopPaginationPending.activePage !== "2" ||
        desktopPaginationPending.busy !== "true" ||
        !desktopPaginationPending.status.includes("Loading page 2") ||
        !desktopPaginationPending.loadingBanner.includes("Loading page 2") ||
        !desktopPaginationPending.firstTranscript.includes("Smoke clip 1") ||
        desktopPaginationPending.scrollY < desktopPaginationPending.scrollYBeforeNext - 96 ||
        desktopPaginationPending.clipsTop > 96
      ) {
        throw new Error(`desktop next-page pending state should stay near the clicked pagination: ${JSON.stringify(desktopPaginationPending)}`);
      }
      holdRecentClipResponses = false;
      releaseRecentClipResponses.splice(0).forEach((release) => release());
      await desktopPaginationPage.waitForFunction(() =>
        document.querySelector("#clips blockquote")?.textContent?.includes("Smoke clip 7"),
      );
      await desktopPaginationPage.waitForFunction(() => {
        const clips = document.querySelector("#clips");
        const tabs = document.querySelector(".tabs");
        const tabsHeight = tabs instanceof HTMLElement ? tabs.getBoundingClientRect().height : 0;
        const clipsTop = clips instanceof HTMLElement ? clips.getBoundingClientRect().top : Number.NaN;
        const minTop = tabsHeight > 0 ? tabsHeight - 4 : -1;
        const maxTop = tabsHeight > 0 ? tabsHeight + 24 : 96;
        return clipsTop >= minTop && clipsTop <= maxTop;
      });
      const desktopPaginationLoaded = await desktopPaginationPage.evaluate(() => ({
        firstTranscript: document.querySelector("#clips blockquote")?.textContent || "",
        activePage: document.querySelector("#clip-pagination button[aria-current='page']")?.textContent?.trim() || "",
        loadingBannerPresent: Boolean(document.querySelector("#clips .clip-page-loading-banner")),
        clipsTop: document.querySelector("#clips")?.getBoundingClientRect().top ?? null,
      }));
      if (
        desktopPaginationLoaded.activePage !== "2" ||
        !desktopPaginationLoaded.firstTranscript.includes("Smoke clip 7") ||
        desktopPaginationLoaded.loadingBannerPresent
      ) {
        throw new Error(`desktop next-page action did not settle on page 2: ${JSON.stringify(desktopPaginationLoaded)}`);
      }
      desktopPaginationState = {
        pending: desktopPaginationPending,
        loaded: desktopPaginationLoaded,
      };
    } finally {
      holdRecentClipResponses = false;
      releaseRecentClipResponses.splice(0).forEach((release) => release());
      await desktopPaginationContext.close();
    }
    await page.locator("#clip-display-controls").getByRole("button", { name: "12", exact: true }).click();
    await page.waitForFunction(() => document.querySelectorAll("#clips .clip-card").length === 12);
    await page.waitForFunction(() => document.querySelector("#clips blockquote")?.textContent?.includes("Smoke clip 1"));
    const twelveClipPage = await page.evaluate(() => ({
      firstTranscript: document.querySelector("#clips blockquote")?.textContent || "",
      renderedClips: document.querySelectorAll("#clips .clip-card").length,
      pageStatus: document.querySelector("#clip-pagination")?.textContent || "",
      activePage: document.querySelector("#clip-pagination button[aria-current='page']")?.textContent?.trim() || "",
    }));
    if (
      twelveClipPage.renderedClips !== 12 ||
      twelveClipPage.activePage !== "1" ||
      !twelveClipPage.firstTranscript.includes("Smoke clip 1")
    ) {
      throw new Error(`12-per-page change did not snap to a page boundary: ${JSON.stringify(twelveClipPage)}`);
    }
    await page.locator("#clip-display-controls").getByRole("button", { name: "24", exact: true }).click();
    await page.waitForFunction(() => document.querySelectorAll("#clips .clip-card").length === 24);
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
        pageSizeButtons: [
          ...headerControls.querySelectorAll(".clip-control-group"),
        ].find((group) => group.textContent?.includes("Clips per page"))?.querySelectorAll("button").length,
      };
    });
    if (
      clipControlsBeforeFlip.renderedClips !== 24 ||
      !clipControlsBeforeFlip.firstTranscript.includes("Smoke clip 1")
    ) {
      throw new Error(`24-per-page change did not snap to page one: ${JSON.stringify(clipControlsBeforeFlip)}`);
    }
    await page.locator("#clip-display-controls").getByRole("button", { name: "Oldest", exact: true }).click();
    await page.waitForFunction(
      () => {
        const activeControl = document
          .querySelector("#clip-display-controls .clip-control-group:last-child button[aria-pressed='true']")
          ?.textContent?.trim();
        return (
          activeControl === "Oldest" &&
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
      activeControl: document
        .querySelector("#clip-display-controls .clip-control-group:last-child button[aria-pressed='true']")
        ?.textContent?.trim(),
    }));
    if (clipControlsBeforeFlip.display !== "grid") {
      throw new Error(`mobile clip controls are not in a grid: ${clipControlsBeforeFlip.display}`);
    }
    if (clipControlsBeforeFlip.inlineControlsPresent) {
      throw new Error(`mobile clip controls were duplicated in the clip list: ${JSON.stringify(clipControlsBeforeFlip)}`);
    }
    if (
      clipControlsBeforeFlip.buttonLabels.includes("48") ||
      !clipControlsBeforeFlip.buttonLabels.includes("24") ||
      clipControlsBeforeFlip.pageSizeButtons !== 3
    ) {
      throw new Error(`mobile page size controls are incomplete: ${JSON.stringify(clipControlsBeforeFlip)}`);
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
      throw new Error(`clip controls did not keep the larger first page: ${JSON.stringify(clipControlsAfterFlip)}`);
    }
    if (await page.getByRole("button", { name: "Fine Tuning" }).count()) {
      throw new Error("Fine Tuning tab should not crowd the primary mobile tabs");
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
      correctionOpen: Boolean(document.querySelector("#clips .clip-card:first-child .transcript-correction")),
    }));
    if (
      !operatorFeatureState.firstTranscript.includes("Smoke clip 1") ||
      operatorFeatureState.buttonText !== "★" ||
      operatorFeatureState.buttonLabel !== "Remove from Hall of Fame" ||
      operatorFeatureState.featuredPill !== "Featured" ||
      !operatorFeatureState.correctionOpen
    ) {
      throw new Error(`operator feature action did not update the clip card: ${JSON.stringify(operatorFeatureState)}`);
    }
    await page.getByRole("tab", { name: "Analysis" }).click();
    await page
      .locator("#lexical-analysis .entity-card:first-child .analysis-correction")
      .waitFor({ state: "visible", timeout: 10000 });
    await page.locator("#lexical-analysis .entity-card:first-child .analysis-correction summary").click();
    await page
      .locator("#lexical-analysis .entity-card:first-child .analysis-correction .transcript-correction-label textarea")
      .fill("Seattle Traffic corrected showcase example.");
    await page.locator("#lexical-analysis .entity-card:first-child .analysis-correction button[type='submit']").click();
    await page.waitForFunction(() =>
      document.querySelector("#lexical-analysis .entity-card:first-child blockquote")?.textContent?.includes("corrected showcase"),
    );
    const operatorAnalysisCorrection = await page.evaluate(() => ({
      summary:
        document
          .querySelector("#lexical-analysis .entity-card:first-child .analysis-correction summary")
          ?.textContent?.trim() || "",
      status:
        document
          .querySelector("#lexical-analysis .entity-card:first-child .analysis-correction .transcript-correction-status")
          ?.textContent?.trim() || "",
      quote: document.querySelector("#lexical-analysis .entity-card:first-child blockquote")?.textContent || "",
    }));
    if (
      operatorAnalysisCorrection.summary !== "Edit correction" ||
      !operatorAnalysisCorrection.status.includes("Saved for manual fine tuning") ||
      !operatorAnalysisCorrection.quote.includes("corrected showcase")
    ) {
      throw new Error(`operator analysis correction did not save: ${JSON.stringify(operatorAnalysisCorrection)}`);
    }
    await page.getByRole("tab", { name: "Performance" }).click();
    await page.locator(".speech-training-panel .performance-card").first().waitFor({ state: "visible", timeout: 10000 });
    const speechTraining = await page.evaluate(() => ({
      title: document.querySelector(".speech-training-panel h3")?.textContent || "",
      cards: [...document.querySelectorAll(".speech-training-panel .performance-card")].map((card) =>
        card.textContent || "",
      ),
      bodyText: document.querySelector(".speech-training-panel")?.textContent || "",
    }));
    const trainingExamplesCard = speechTraining.cards.find((card) => card.includes("Training examples")) || "";
    if (!trainingExamplesCard.includes("3") || trainingExamplesCard.includes("3 / 20")) {
      throw new Error(`performance speech training correction card missing: ${JSON.stringify(speechTraining)}`);
    }
    if (!speechTraining.cards.some((card) => card.includes("Last ASR run") && card.includes("skipped"))) {
      throw new Error(`performance speech training last-run card missing: ${JSON.stringify(speechTraining)}`);
    }
    if (speechTraining.bodyText.includes("Export JSONL") || speechTraining.bodyText.includes("Nightly training")) {
      throw new Error(`performance speech training panel kept bulky operator actions: ${JSON.stringify(speechTraining)}`);
    }
    await page.getByRole("tab", { name: "About" }).click();
    await page.locator("#panel-about .about-link").waitFor({ state: "visible", timeout: 10000 });
    const aboutState = await page.evaluate(() => ({
      pathname: window.location.pathname,
      hidden: document.querySelector("#panel-about")?.hidden ?? true,
      activeTab: document.querySelector(".tab.is-active")?.textContent?.trim() || "",
      linkHref: document.querySelector("#panel-about .about-link")?.getAttribute("href") || "",
      linkText: document.querySelector("#panel-about .about-link")?.textContent?.trim() || "",
      bodyText: document.querySelector("#panel-about")?.textContent || "",
    }));
    if (
      aboutState.pathname !== "/about/" ||
      aboutState.hidden ||
      aboutState.activeTab !== "About" ||
      aboutState.linkHref !== "https://robertboscacci.com/projects/elliott-bay-vhf/" ||
      aboutState.linkText !== "Read the full project write-up" ||
      !aboutState.bodyText.includes("Raspberry Pi radio edge") ||
      !aboutState.bodyText.includes("Ubuntu micro-computer") ||
      !aboutState.bodyText.includes("Whisper") ||
      !aboutState.bodyText.includes("whisper-large-v3-turbo") ||
      !aboutState.bodyText.includes("CTranslate2/faster-whisper")
    ) {
      throw new Error(`about tab did not expose the project write-up: ${JSON.stringify(aboutState)}`);
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
      if (searchResult.audioCount < 1) {
        throw new Error(`search result audio controls did not render: ${JSON.stringify(searchResult)}`);
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
    console.log(
      JSON.stringify(
        {
          status: "ok",
          baseUrl,
          lazyClipShell,
          liveCatchupState,
          liveSelectorState,
          allButTrafficState,
          ...result,
          clipControls: {
            initialPagination,
            secondPagePagination,
            pendingPagination,
            oldestPagePagination,
            desktopPaginationState,
            beforeFlip: clipControlsBeforeFlip,
            afterFlip: clipControlsAfterFlip,
          },
          aboutState,
          directAnalysisCorrection,
          speechTraining,
          searchDefaultState,
          performanceHover,
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
  const limit = Math.min(Math.max(Number(url.searchParams.get("limit") || 6), 1), 100);
  const page = Math.max(Number(url.searchParams.get("page") || 1), 1);
  const offset = Math.max(
    Number(url.searchParams.get("offset") || (page - 1) * limit),
    0,
  );
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
  const reviewedOnly = url.searchParams.get("reviewed") === "true";
  const oldestFirst = url.searchParams.get("sort") === "oldest";
  const indexes = Array.from({ length: total }, (_value, index) => index).filter((index) => {
    if (featuredOnly && !featuredClipIndexes.has(index)) {
      return false;
    }
    if (reviewedOnly && !reviewedClipIndexes.has(index)) {
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
  return {
    clips: indexes
      .slice(offset, offset + limit)
      .map((index) => recentClip(index, payloadChannels[index % payloadChannels.length] || "14")),
    clip_count: total,
    filtered_clip_count: filteredTotal,
    featured: featuredOnly,
    reviewed: reviewedOnly,
    channel_counts: Object.fromEntries(payloadChannels.map((channel) => [channel, filteredTotal])),
    channel_labels: Object.fromEntries(
      payloadChannels.map((channel) => [channel, channel === "14" ? "Vessel Traffic Service" : "Non-traffic"]),
    ),
    limit,
    offset,
    page,
  };
}

function recentClip(index, channel = "14") {
  const startedAt = new Date(Date.parse("2026-05-31T20:00:00Z") - index * 60000).toISOString();
  const reviewed = reviewedClipIndexes.has(index);
  const displayTranscript = reviewed ? `Smoke clip ${index + 1} reviewed` : `Smoke clip ${index + 1}`;
  return {
    id: `clip-${index + 1}`,
    channel,
    channel_label: channel === "14" ? "Vessel Traffic Service" : "Non-traffic",
    started_at: startedAt,
    ended_at: new Date(Date.parse(startedAt) + 15000).toISOString(),
    duration_seconds: 15,
    transcript: displayTranscript,
    transcript_public: displayTranscript,
    transcript_reviewed: reviewed,
    include_in_training: reviewed,
    training_quality: reviewed ? "good" : "unknown",
    training_split: "auto",
    training_flags: [],
    training_reason: reviewed ? "smoke reviewed example" : null,
    featured: featuredClipIndexes.has(index),
    featured_at: featuredClipIndexes.has(index) ? "2026-06-01T12:00:00Z" : null,
    playback_url: "",
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
    started_at: new Date(Date.parse("2026-05-31T20:00:00Z") - clipIndex * 60000).toISOString(),
    featured,
  };
}

async function transcriptCorrectionPayload(request) {
  const rawBody = await readRequestBody(request);
  const payload = JSON.parse(rawBody || "{}");
  const clipIndex = clipIndexForStartedAt(String(payload.started_at || ""));
  if (payload.include_in_training !== true || payload.training_quality !== "good") {
    return {
      status: "invalid_training_metadata",
      expected: { include_in_training: true, training_quality: "good" },
      received: {
        include_in_training: payload.include_in_training,
        training_quality: payload.training_quality,
      },
    };
  }
  if (clipIndex >= 0) {
    reviewedClipIndexes.add(clipIndex);
  }
  return {
    status: "ok",
    channel: payload.channel || "14",
    started_at: payload.started_at || "",
    original_transcript:
      clipIndex >= 0 ? `Smoke clip ${clipIndex + 1}` : payload.transcript || "",
    corrected_transcript: payload.transcript || "",
    reviewed_by: payload.reviewer || "operator-ui",
    transcript_reviewed: true,
    include_in_training: true,
    training_quality: "good",
    training_split: payload.training_split || "auto",
    training_flags: Array.isArray(payload.training_flags) ? payload.training_flags : [],
    training_reason: payload.training_reason || null,
  };
}

async function transcriptCorrectionDeletePayload(request) {
  const rawBody = await readRequestBody(request);
  const payload = JSON.parse(rawBody || "{}");
  const clipIndex = clipIndexForStartedAt(String(payload.started_at || ""));
  if (clipIndex >= 0) {
    reviewedClipIndexes.delete(clipIndex);
  }
  const transcript = clipIndex >= 0 ? `Smoke clip ${clipIndex + 1}` : "";
  return {
    status: "uncorrected",
    channel: payload.channel || "14",
    started_at: payload.started_at || "",
    original_transcript: transcript,
    corrected_transcript: payload.transcript || "",
    transcript,
    transcript_reviewed: false,
    include_in_training: false,
  };
}

function clipIndexForStartedAt(startedAt) {
  const parsedMs = Date.parse(startedAt);
  if (!Number.isFinite(parsedMs)) {
    return -1;
  }
  const baseMs = Date.parse("2026-05-31T20:00:00Z");
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

function asrFeedbackStatusPayload() {
  return {
    status: "ok",
    reviewed_correction_count: 3,
    min_corrections: 20,
    ready_for_training: false,
    base_model: "openai/whisper-large-v3-turbo",
    nightly_schedule: "manual only",
    export_url: "/api/clips/corrections/export",
    training_status: {
      status: "skipped",
      reason: "not enough reviewed transcript corrections",
      correction_count: 3,
      min_corrections: 20,
      generated_at: "2026-06-01T03:20:00Z",
    },
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

function lexicalPayload() {
  return {
    status: "ok",
    generated_at: "2026-05-31T20:01:00Z",
    source_clip_count: 2,
    channels: { "14": 2 },
    frequency: {
      by_channel: { "14": 2 },
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
    relativePath === "/reviewed/" ||
    relativePath === "/reviewed" ||
    relativePath === "/search/" ||
    relativePath === "/search" ||
    relativePath === "/operator/" ||
    relativePath === "/operator" ||
    relativePath === "/performance/" ||
    relativePath === "/performance" ||
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
