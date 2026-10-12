import assert from "node:assert/strict";
import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { createRequire } from "node:module";
const { chromium } = createRequire(path.join(process.env.TALKINGBOATS_BROWSER_DEPENDENCY_ROOT || process.cwd(), "package.json"))("playwright");

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const base = process.env.TALKINGBOATS_ASR_SMOKE_BASE_URL || "https://dev.seattleboatradio.com";
const browser = await chromium.launch({ headless: true });
const context = await browser.newContext();
const page = await context.newPage();
const errors = [];
page.on("pageerror", (error) => errors.push(error.message));
try {
  const channelsResponse = await page.request.get(`${base}/api/live/channels`);
  assert.equal(channelsResponse.status(), 200);
  const channels = (await channelsResponse.json()).channels.map((row) => row.channel);
  assert(channels.includes("14") && channels.includes("13") && channels.includes("16"));
  assert(!channels.includes("74"));
  assert([6, 8].includes(channels.length));
  const forbidden = await page.request.get(`${base}/api/clips/recent?channels=74&quality=all&include_playback_url=false`);
  assert.deepEqual((await forbidden.json()).clips, []);
  await page.goto(`${base}/performance/`, { waitUntil: "domcontentloaded" });
  const panel = page.locator(".asr-experiments");
  await panel.getByRole("button", { name: "Refresh experiments" }).click();
  await panel.getByRole("status").filter({ hasText: "Reviewed audio:" }).waitFor();
  assert(await panel.getByRole("button", { name: "Train and compare Turbo" }).isDisabled());
  await Promise.all(channels.map(async (channel) => {
    const response = await page.request.get(`${base}/api/live/${channel}/status`);
    assert.equal(response.status(), 200);
    const live = await page.evaluate(async (channelNumber) => {
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), 10000);
      try {
        const response = await fetch(`/api/live/${channelNumber}/current.mp3`, { signal: controller.signal });
        const reader = response.body.getReader();
        const first = await reader.read();
        await reader.cancel();
        return { status: response.status, bytes: first.value?.length || 0 };
      } finally { clearTimeout(timer); controller.abort(); }
    }, channel);
    assert.equal(live.status, 200);
    assert(live.bytes > 0, `Live feed ${channel} must deliver audio`);
  }));
  // Isolated experiment controls and archived range audio; no actual job or label is created.
  const actualStatus = await (await page.request.get(`${base}/api/asr-feedback/status`)).json();
  const experimentId = "f".repeat(32);
  const exampleId = "e".repeat(64);
  let experiment = null;
  const wav = Buffer.alloc(44 + 48000);
  wav.write("RIFF", 0); wav.writeUInt32LE(wav.length - 8, 4); wav.write("WAVEfmt ", 8);
  wav.writeUInt32LE(16, 16); wav.writeUInt16LE(1, 20); wav.writeUInt16LE(1, 22);
  wav.writeUInt32LE(8000, 24); wav.writeUInt32LE(16000, 28); wav.writeUInt16LE(2, 32);
  wav.writeUInt16LE(16, 34); wav.write("data", 36); wav.writeUInt32LE(48000, 40);
  for (let n = 0; n < 24000; n++) wav.writeInt16LE(Math.round(500 * Math.sin(n * Math.PI / 20)), 44 + n * 2);
  await page.route("**/api/asr-feedback/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    if (url.pathname.endsWith("/audio")) return route.fulfill({ body: wav, contentType: "audio/wav" });
    if (url.pathname.endsWith("/status")) return route.fulfill({ json: {
      ...actualStatus, ready: true, runs: experiment ? [experiment] : [],
    } });
    if (url.pathname.endsWith("/cancel")) experiment = { ...experiment, status: "cancelled", reason: "Cancelled fixture" };
    else if (request.method() === "POST") experiment = { id: experimentId, status: "queued", eligible: false };
    return route.fulfill({ json: experiment });
  });
  await panel.getByRole("button", { name: "Refresh experiments" }).click();
  await panel.getByRole("button", { name: "Train and compare Turbo" }).click();
  await panel.locator("h3", { hasText: "queued" }).waitFor();
  await panel.getByRole("button", { name: "Cancel experiment" }).click();
  await panel.locator("h3", { hasText: "cancelled" }).waitFor();
  const metric = { entity_errors: 1, entity_mentions: 50, invented_names: 0, wer: 0.1,
    word_errors: 1, real_time_factor: 2, examples: [] };
  experiment = { id: experimentId, status: "completed", eligible: false, metrics: {
    turbo: metric, turbo_with_hints: metric, candidate_with_hints: { ...metric, examples: [{
      id: exampleId, reference: "Osprey northbound", prediction: "Osprey northbound",
      audio_start_seconds: 1, audio_end_seconds: 2,
    }] },
  } };
  await panel.getByRole("button", { name: "Refresh experiments" }).click();
  const reviewedAudio = panel.locator('audio[aria-label="Reviewed range audio"]');
  await reviewedAudio.waitFor({ state: "attached" });
  await reviewedAudio.evaluate((audio) => { audio.load(); });
  await page.waitForFunction(() => document.querySelector('audio[aria-label="Reviewed range audio"]')?.readyState > 0);
  await page.waitForFunction(() => {
    const audio = document.querySelector('audio[aria-label="Reviewed range audio"]');
    return audio && !audio.seeking && Math.abs(audio.currentTime - 1) < 0.1;
  });
  await reviewedAudio.evaluate((audio) => audio.play());
  await page.waitForFunction(() => {
    const audio = document.querySelector('audio[aria-label="Reviewed range audio"]');
    return audio?.paused && audio.currentTime >= 2;
  });
  // Isolated editor fixture: no write touches the shared production corpus.
  const fixture = { channel: "14", started_at: "2026-10-05T12:00:00Z", ended_at: "2026-10-05T12:00:05Z",
    duration_seconds: 5, transcript: "Tug spray northbound", original: "Tug spray northbound", revision: 0, production_overlay_active: true };
  await page.route("**/api/clips/recent?**", async (route) => route.fulfill({ json: {
    clips: [{ ...fixture, correction_revision: fixture.revision }], clip_count: 1, analyzed_clip_count: 1,
    channel_labels: { "14": "VTS / Seattle Traffic" }, next_cursor: null, counts_deferred: true,
  } }));
  await page.route("**/api/clips/corrections**", async (route) => {
    if (route.request().method() === "PUT") {
      const body = route.request().postDataJSON();
      assert.equal(body.expected_revision, fixture.revision);
      fixture.revision += 1;
      fixture.text = body.reverted ? fixture.original : body.text;
      fixture.transcript = fixture.text;
      fixture.reverted = body.reverted;
    }
    await route.fulfill({ json: { ...fixture, text: fixture.text || fixture.transcript } });
  });
  await page.goto(`${base}/clips/`, { waitUntil: "domcontentloaded" });
  const card = page.locator(".clip-card").first();
  await card.locator("summary", { hasText: "Correct transcript" }).click();
  await card.getByRole("textbox", { name: "Corrected transcript", exact: true }).fill("Tug Osprey northbound");
  await card.getByRole("button", { name: "Save correction" }).click();
  await card.getByRole("status").filter({ hasText: "Saved on dev and production" }).waitFor();
  assert.equal(await card.locator("blockquote").textContent(), "Tug Osprey northbound");
  await page.reload({ waitUntil: "domcontentloaded" });
  await page.locator(".clip-card blockquote", { hasText: "Tug Osprey northbound" }).first().waitFor();
  await page.locator(".clip-card").first().locator("summary", { hasText: "Correct transcript" }).click();
  await page.locator(".clip-card").first().getByRole("button", { name: "Restore original" }).click();
  await page.getByRole("status").filter({ hasText: "Original restored" }).waitFor();
  assert.equal(await page.locator(".clip-card blockquote").first().textContent(), fixture.original);
  // Exercise the newly packaged browser shell with a public hostname and the same isolated overlay.
  const publicContext = await browser.newContext();
  const publicPage = await publicContext.newPage();
  await publicPage.route("https://seattleboatradio.com/**", async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname === "/" || url.pathname === "/clips/") {
      return route.fulfill({ contentType: "text/html", body: await fs.readFile(path.join(root, "public-site/index.html"), "utf8") });
    }
    if (["/assets/app.js", "/assets/styles.css"].includes(url.pathname)) {
      return route.fulfill({ contentType: url.pathname.endsWith(".js") ? "text/javascript" : "text/css", body: await fs.readFile(path.join(root, "public-site", url.pathname.slice(1)), "utf8") });
    }
    if (url.pathname === "/api/clips/recent") return route.fulfill({ json: {
      clips: [{ ...fixture, transcript: "Tug Osprey northbound" }], next_cursor: null,
      clip_count: 1, channel_labels: { "14": "VTS / Seattle Traffic" }, counts_deferred: true,
    } });
    return route.fulfill({ status: 404, json: { detail: "isolated public fixture" } });
  });
  await publicPage.goto("https://seattleboatradio.com/clips/", { waitUntil: "domcontentloaded" });
  await publicPage.locator(".clip-card blockquote", { hasText: "Tug Osprey northbound" }).waitFor();
  assert.equal(await publicPage.locator(".correction-editor").count(), 0);
  assert.equal(await publicPage.locator(".asr-experiments").count(), 0);
  assert.deepEqual(errors, []);
  await publicContext.close();
  console.log("event=asr_dev_playwright_passed real_dev_reads=true isolated_editor_and_public_overlay=true");
} catch (error) {
  const directory = path.join(root, "outputs/asr-smoke");
  await fs.mkdir(directory, { recursive: true });
  await page.screenshot({ path: path.join(directory, "failure.png"), fullPage: true });
  throw error;
} finally {
  await context.close();
  await browser.close();
}
