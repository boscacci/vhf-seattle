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
let topicClusterReturnsNotFound = false;
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
      if (holdRecentClipResponses) {
        await new Promise((resolve) => {
          releaseRecentClipResponses.push(resolve);
        });
      }
      return sendJson(response, recentClipPayload(url));
    }
    if (url.pathname === "/api/clips/search") {
      return sendJson(response, searchPayload(url));
    }
    if (url.pathname === "/api/asr-feedback/status") {
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
        return sendJson(response, { detail: "Not Found" }, 404);
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
    if (!lazyClipShell.controlsText.includes("Clips per page") || !lazyClipShell.controlsText.includes("48")) {
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
        panel.querySelector("h3")?.textContent?.includes("Transcript topics"),
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
    if (result.transcriptTopics.bodyText.includes("Descriptive NLP summary")) {
      throw new Error("removed descriptive NLP copy is still present");
    }
    if (!["pan-x pan-y pinch-zoom", "manipulation"].includes(result.topicFrame.touchAction)) {
      throw new Error(`topic iframe blocks pinch zoom: ${result.topicFrame.touchAction}`);
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
    await page.getByRole("button", { name: "Clip Review" }).click();
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
        ellipsisCount: pagination.querySelectorAll(".pagination-ellipsis").length,
      };
    });
    if (!initialPagination.text.includes("Newest") || !initialPagination.text.includes("Oldest")) {
      throw new Error(`pagination jump buttons missing: ${JSON.stringify(initialPagination)}`);
    }
    if (!initialPagination.buttons.some((button) => button.text === "1" && button.current === "page")) {
      throw new Error(`pagination current page button missing: ${JSON.stringify(initialPagination)}`);
    }
    if (initialPagination.buttons.some((button) => button.text === "12")) {
      throw new Error(`pagination kept a redundant last-page anchor: ${JSON.stringify(initialPagination)}`);
    }
    if (initialPagination.ellipsisCount < 1) {
      throw new Error(`pagination ellipsis missing: ${JSON.stringify(initialPagination)}`);
    }
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
    }));
    if (
      pendingPagination.activePage !== "7" ||
      pendingPagination.busy !== "true" ||
      !pendingPagination.status.includes("Loading page 7")
    ) {
      throw new Error(`pagination did not provide immediate pending feedback: ${JSON.stringify(pendingPagination)}`);
    }
    if (!pendingPagination.firstTranscript.includes("Smoke clip 31")) {
      throw new Error(`pagination pending state should not flicker away the current cards: ${JSON.stringify(pendingPagination)}`);
    }
    holdRecentClipResponses = false;
    releaseRecentClipResponses.splice(0).forEach((release) => release());
    await page.waitForFunction(() => document.querySelector("#clips blockquote")?.textContent?.includes("Smoke clip 37"));
    await page.locator("#clip-pagination").getByRole("button", { name: "Newest page" }).click();
    await page.waitForFunction(() => document.querySelector("#clips blockquote")?.textContent?.includes("Smoke clip 1"));
    await page.locator("#clip-pagination").getByRole("button", { name: "Oldest page" }).click();
    await page.waitForFunction(() => document.querySelector("#clips blockquote")?.textContent?.includes("Smoke clip 67"));
    const oldestPagePagination = await page.evaluate(() => ({
      firstTranscript: document.querySelector("#clips blockquote")?.textContent || "",
      activePage: document.querySelector("#clip-pagination button[aria-current='page']")?.textContent?.trim() || "",
      text: document.querySelector("#clip-pagination")?.textContent || "",
      numberedButtons: [...document.querySelectorAll("#clip-pagination .pagination-page-button")].map((button) =>
        button.textContent?.trim(),
      ),
    }));
    if (oldestPagePagination.activePage !== "12") {
      throw new Error(`pagination oldest jump did not land on last page: ${JSON.stringify(oldestPagePagination)}`);
    }
    if (oldestPagePagination.numberedButtons.join(",") !== "8,9,10,11,12") {
      throw new Error(`pagination oldest window should show five nearby pages only: ${JSON.stringify(oldestPagePagination)}`);
    }
    await page.locator("#clip-pagination").getByRole("button", { name: "Newest page" }).click();
    await page.waitForFunction(() => document.querySelector("#clips blockquote")?.textContent?.includes("Smoke clip 1"));
    await page.locator("#clip-display-controls").getByRole("button", { name: "48", exact: true }).click();
    await page.waitForFunction(() => document.querySelectorAll("#clips .clip-card").length === 48);
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
        pageStatus: document.querySelector("#clip-pagination")?.textContent || "",
        buttonLabels: [...headerControls.querySelectorAll("button")].map((button) =>
          button.textContent?.trim(),
        ),
        pageSizeButtons: [...headerControls.querySelectorAll(".clip-control-group:first-child button")].length,
      };
    });
    await page.locator("#clip-display-controls").getByRole("button", { name: "Oldest", exact: true }).click();
    await page.waitForFunction(
      () =>
        document
          .querySelector("#clip-display-controls .clip-control-group:last-child button[aria-pressed='true']")
          ?.textContent?.trim() === "Oldest",
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
    if (!clipControlsBeforeFlip.buttonLabels.includes("48") || clipControlsBeforeFlip.pageSizeButtons !== 4) {
      throw new Error(`mobile page size controls are incomplete: ${JSON.stringify(clipControlsBeforeFlip)}`);
    }
    if (!clipControlsBeforeFlip.firstTranscript.includes("Smoke clip 1")) {
      throw new Error(`expected newest page order before flip: ${clipControlsBeforeFlip.firstTranscript}`);
    }
    if (!clipControlsAfterFlip.firstTranscript.includes("Smoke clip 48")) {
      throw new Error(`expected oldest page order after flip: ${clipControlsAfterFlip.firstTranscript}`);
    }
    if (clipControlsAfterFlip.renderedClips !== 48 || !clipControlsAfterFlip.pageStatus.includes("Page 1")) {
      throw new Error(`clip controls did not keep the larger first page: ${JSON.stringify(clipControlsAfterFlip)}`);
    }
    if (await page.getByRole("button", { name: "Fine Tuning" }).count()) {
      throw new Error("Fine Tuning tab should not crowd the primary mobile tabs");
    }
    await page.getByRole("button", { name: "Performance" }).click();
    await page.locator(".speech-training-panel .performance-card").first().waitFor({ state: "visible", timeout: 10000 });
    const speechTraining = await page.evaluate(() => ({
      title: document.querySelector(".speech-training-panel h3")?.textContent || "",
      cards: [...document.querySelectorAll(".speech-training-panel .performance-card")].map((card) =>
        card.textContent || "",
      ),
      bodyText: document.querySelector(".speech-training-panel")?.textContent || "",
    }));
    if (!speechTraining.cards.some((card) => card.includes("Reviewed corrections") && card.includes("3 / 20"))) {
      throw new Error(`performance speech training correction card missing: ${JSON.stringify(speechTraining)}`);
    }
    if (!speechTraining.cards.some((card) => card.includes("Last ASR run") && card.includes("skipped"))) {
      throw new Error(`performance speech training last-run card missing: ${JSON.stringify(speechTraining)}`);
    }
    if (speechTraining.bodyText.includes("Export JSONL") || speechTraining.bodyText.includes("Nightly training")) {
      throw new Error(`performance speech training panel kept bulky operator actions: ${JSON.stringify(speechTraining)}`);
    }
    const desktopPerformanceContext = await browser.newContext({ viewport: { width: 1280, height: 900 } });
    let performanceHover = null;
    let defaultRangeState = null;
    let shortRangeState = null;
    let longRangeState = null;
    try {
      const desktopPerformancePage = await desktopPerformanceContext.newPage();
      await desktopPerformancePage.goto(`${baseUrl}/search/`);
      await desktopPerformancePage.getByLabel("Search transcript meaning").fill("tug barge");
      await desktopPerformancePage.getByRole("button", { name: "Search clips", exact: true }).click();
      await desktopPerformancePage.locator(".search-result-card").first().waitFor({ state: "visible", timeout: 10000 });
      const searchResult = await desktopPerformancePage.evaluate(() => ({
        status: document.querySelector("#clip-search-status")?.textContent || "",
        resultCount: document.querySelectorAll(".search-result-card").length,
        firstTranscript: document.querySelector(".search-result-card blockquote")?.textContent || "",
        audioCount: document.querySelectorAll(".search-result-card audio").length,
      }));
      if (!searchResult.status.includes("semantic matches") || searchResult.resultCount < 1) {
        throw new Error(`search results did not render: ${JSON.stringify(searchResult)}`);
      }
      if (!searchResult.firstTranscript.includes("Smoke search")) {
        throw new Error(`search result transcript did not come from search API: ${JSON.stringify(searchResult)}`);
      }
      if (searchResult.audioCount < 1) {
        throw new Error(`search result audio controls did not render: ${JSON.stringify(searchResult)}`);
      }
      await desktopPerformancePage.getByRole("button", { name: "Performance" }).click();
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
      if (!performanceHover.hostTitles.includes("OptiPlex ASR Box")) {
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
          ...result,
          clipControls: {
            initialPagination,
            secondPagePagination,
            oldestPagePagination,
            beforeFlip: clipControlsBeforeFlip,
            afterFlip: clipControlsAfterFlip,
          },
          speechTraining,
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
  const offset = Math.max(Number(url.searchParams.get("offset") || 0), 0);
  const total = 72;
  return {
    clips: Array.from({ length: Math.max(0, Math.min(limit, total - offset)) }, (_value, index) =>
      recentClip(offset + index),
    ),
    clip_count: total,
    filtered_clip_count: total,
    channel_counts: { "14": total },
    channel_labels: { "14": "Vessel Traffic Service" },
    limit,
    offset,
  };
}

function recentClip(index) {
  const startedAt = new Date(Date.parse("2026-05-31T20:00:00Z") - index * 60000).toISOString();
  return {
    id: `clip-${index + 1}`,
    channel: "14",
    channel_label: "Vessel Traffic Service",
    started_at: startedAt,
    ended_at: new Date(Date.parse(startedAt) + 15000).toISOString(),
    duration_seconds: 15,
    transcript: `Smoke clip ${index + 1}`,
    transcript_public: `Smoke clip ${index + 1}`,
    playback_url: "",
  };
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
    base_model: "openai/whisper-small.en",
    nightly_schedule: "03:20 UTC",
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
        role: "OptiPlex ASR Box",
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
        communication_markers: [{ term: "roger", count: 1 }],
        movement: [],
        places: [],
        vessel_types: [],
      },
      bigrams: [],
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
    ],
    topics: {
      status: "ok",
      plot_url: "/analysis/topic_clusters.html",
      items: [{ id: 0, label: "Seattle Traffic / pilots", count: 2, top_words: ["Seattle Traffic"] }],
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
    relativePath === "/analysis/" ||
    relativePath === "/analysis"
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
