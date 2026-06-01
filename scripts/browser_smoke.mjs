#!/usr/bin/env node
import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import { extname, join, normalize } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const repoRoot = fileURLToPath(new URL("..", import.meta.url));
const publicSiteRoot = join(repoRoot, "public-site");
const audioStartedAt = "2026-05-31T20:00:00Z";
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
      return sendJson(response, recentClipPayload(url));
    }
    if (url.pathname === "/api/live/channels") {
      return sendJson(response, { channels: [] });
    }
    if (url.pathname === "/analysis/topic_clusters.html") {
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
    await page.getByRole("button", { name: "48" }).click();
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
    await page.getByRole("button", { name: "Oldest" }).click();
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
    console.log(
      JSON.stringify(
        {
          status: "ok",
          baseUrl,
          ...result,
          clipControls: {
            beforeFlip: clipControlsBeforeFlip,
            afterFlip: clipControlsAfterFlip,
          },
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
  if (relativePath === "/" || relativePath === "/analysis/" || relativePath === "/analysis") {
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

function sendJson(response, payload) {
  response.writeHead(200, {
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
