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
  for (const channel of channels) {
    const response = await page.request.get(`${base}/api/live/${channel}/status`);
    assert.equal(response.status(), 200);
  }
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
