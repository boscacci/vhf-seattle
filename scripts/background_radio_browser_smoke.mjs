import assert from "node:assert/strict";
import fs from "node:fs/promises";
import path from "node:path";

// This exercises lifecycle events and native audio in mobile browser contexts.
// An emulated context cannot prove physical iOS/Android screen-lock behavior.
export async function verifyBackgroundRadio(browser, base, failureDirectory = "/tmp/talkingboats-background-radio-smoke") {
  const profiles = [
    { name: "iphone", userAgent: "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 Version/18.0 Mobile/15E148 Safari/604.1" },
    { name: "android", userAgent: "Mozilla/5.0 (Linux; Android 15; Pixel 9) AppleWebKit/537.36 Chrome/130.0.0.0 Mobile Safari/537.36" },
  ];
  await Promise.all(profiles.map(async profile => {
    const context = await browser.newContext({ userAgent: profile.userAgent,
      viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });
    const page = await context.newPage();
    const errors = [];
    page.on("pageerror", error => errors.push(error.message));
    try {
      await page.addInitScript(() => {
        window.__radioActions = {};
        const session = navigator.mediaSession;
        const original = session.setActionHandler.bind(session);
        session.setActionHandler = (action, handler) => {
          window.__radioActions[action] = handler;
          original(action, handler);
        };
        window.__audioGraphsCreated = 0;
        const Constructor = window.AudioContext;
        if (Constructor) window.AudioContext = new Proxy(Constructor, {
          construct(target, args) { window.__audioGraphsCreated++; return Reflect.construct(target, args); },
        });
      });
      const wave = seconds => {
        const buffer = Buffer.alloc(44 + 16000 * seconds);
        buffer.write("RIFF", 0); buffer.writeUInt32LE(buffer.length - 8, 4);
        buffer.write("WAVEfmt ", 8); buffer.writeUInt32LE(16, 16);
        buffer.writeUInt16LE(1, 20); buffer.writeUInt16LE(1, 22);
        buffer.writeUInt32LE(8000, 24); buffer.writeUInt32LE(16000, 28);
        buffer.writeUInt16LE(2, 32); buffer.writeUInt16LE(16, 34);
        buffer.write("data", 36); buffer.writeUInt32LE(buffer.length - 44, 40);
        return buffer;
      };
      let clip = null;
      await page.route("**/api/clips/recent?*", route => route.fulfill({ json: {
        clips: clip ? [clip] : [], counts_deferred: true, next_cursor: null,
      } }));
      await page.route("**/api/clips/audio?*", route => route.fulfill({ body: wave(1), contentType: "audio/wav" }));
      await page.route("**/api/live/16/current.mp3*", route => route.fulfill({ body: wave(20), contentType: "audio/wav" }));
      await page.goto(`${base}/live/`, { waitUntil: "domcontentloaded" });
      await page.waitForFunction(() => document.querySelectorAll("#live-channel-picker button").length === 18);
      assert(await page.locator("#system-media-controls").isChecked());
      await page.locator("#play-live").click();
      await page.waitForFunction(() => {
        const audio = document.querySelector("#live-audio");
        return audio.loop && !audio.paused && audio.currentTime > 0 && navigator.mediaSession.playbackState === "playing";
      });
      await page.evaluate(() => {
        Object.defineProperty(document, "hidden", { configurable: true, get: () => true });
        document.dispatchEvent(new Event("visibilitychange"));
        window.dispatchEvent(new PageTransitionEvent("pagehide", { persisted: true }));
        window.__originalRadioElement = document.querySelector("#live-audio");
      });
      assert(await page.locator("#live-audio").evaluate(audio => !audio.paused && audio.loop));
      clip = { id: `background-${profile.name}`, channel: "16", started_at: new Date().toISOString(),
        audio_url: "/background-fixture.wav", duration_seconds: 1 };
      // Exercise the ordinary polling path while the document reports hidden.
      await page.waitForResponse(response => response.url().includes("/api/clips/audio?") && response.status() === 200);
      await page.waitForFunction(() => {
        const audio = document.querySelector("#live-audio");
        return !audio.loop && !audio.paused && audio.currentTime > 0;
      });
      await page.waitForFunction(() => {
        const audio = document.querySelector("#live-audio");
        return audio.loop && !audio.paused;
      });
      await page.evaluate(() => window.__radioActions.pause());
      await page.waitForTimeout(5200);
      assert(await page.locator("#live-audio").evaluate(audio => audio.paused && !audio.loop && audio.hasAttribute("src")));
      assert.equal(await page.evaluate(() => navigator.mediaSession.playbackState), "paused");
      clip = null;
      await page.evaluate(() => window.__radioActions.play());
      await page.waitForFunction(() => !document.querySelector("#live-audio").paused);
      await page.evaluate(() => document.querySelector("#live-audio").pause());
      await page.waitForFunction(() => navigator.mediaSession.playbackState === "paused");
      await page.waitForTimeout(100);
      assert(await page.locator("#live-audio").evaluate(audio => audio.paused));
      await page.locator(".live-advanced-channel-selector > summary").click();
      await page.locator('#live-channel-picker [data-channel="16"]').click();
      await page.locator("#play-live").click();
      await page.waitForFunction(() => !document.querySelector("#live-audio").paused);
      await page.evaluate(() => document.dispatchEvent(new Event("visibilitychange")));
      assert(await page.locator("#live-audio").evaluate(audio => !audio.paused && !audio.loop));
      await page.evaluate(() => window.__radioActions.stop());
      assert(await page.locator("#live-audio").evaluate(audio => audio.paused && !audio.hasAttribute("src")));
      assert.equal(await page.evaluate(() => navigator.mediaSession.playbackState), "none");
      assert.equal(await page.evaluate(() => document.querySelector("#live-audio") === window.__originalRadioElement), true);
      assert.equal(await page.evaluate(() => window.__audioGraphsCreated), 0);
      assert.deepEqual(errors, []);
    } catch (error) {
      await fs.mkdir(failureDirectory, { recursive: true, mode: 0o700 });
      await page.screenshot({ path: path.join(failureDirectory, `${profile.name}-failure.png`), fullPage: true }).catch(() => {});
      throw error;
    } finally {
      await context.close();
    }
  }));
  console.log("event=background_radio_playwright_passed profiles=iphone,android physical_lock_test=false");
}
