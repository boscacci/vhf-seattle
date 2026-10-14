import assert from "node:assert/strict";
import { createRequire } from "node:module";
import path from "node:path";
const { chromium } = createRequire(path.join(process.env.TALKINGBOATS_BROWSER_DEPENDENCY_ROOT || process.cwd(), "package.json"))("playwright");
const base = process.env.TALKINGBOATS_DOCKTALK_SMOKE_BASE_URL || "https://seattleboatradio.com";
const browser = await chromium.launch({ headless: true });
try {
  for (const viewport of [{width:390,height:844},{width:1440,height:900}]) {
    const page=await browser.newPage({viewport});const errors=[];page.on("pageerror",e=>errors.push(e.message));
    const rows=(await (await page.request.get(`${base}/api/live/channels`)).json()).channels;
    assert.equal(rows.length,18);assert.equal(rows.filter(row=>row.recorded).length,9);assert(!rows.some(row=>row.channel==="74"));
    await page.goto(`${base}/live/`,{waitUntil:"domcontentloaded"});
    await page.locator(".live-advanced-channel-selector > summary").click();
    await page.waitForFunction(()=>document.querySelectorAll("#live-channel-picker .live-channel-option").length===18);
    assert.equal(await page.locator("#live-channel-picker .live-channel-option",{hasText:"Live only"}).count(),9);
    for(const row of rows) {
      const received=await page.evaluate(async channel=>{
        const controller=new AbortController();const timer=setTimeout(()=>controller.abort(),15000);
        try{const response=await fetch(`/api/live/${channel}/current.mp3`,{signal:controller.signal});const reader=response.body.getReader();const first=await reader.read();await reader.cancel();return {status:response.status,bytes:first.value?.length||0};}
        finally{clearTimeout(timer);controller.abort();}
      },row.channel);
      assert.equal(received.status,200);assert(received.bytes>0);
    }
    assert(await page.locator("#live-primary-channel-picker").getByRole("button",{name:"All recorded channels"}).count());
    await page.locator('#live-channel-picker [data-channel="06"]').click();
    await page.locator("#live-last-communication",{hasText:"Live only · no saved clips"}).waitFor();
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
    assert.deepEqual(errors,[]);await page.close();
  }
  console.log("event=docktalk_production_playwright_passed real_live_channels=18 recorded_channels=9");
} finally {await browser.close();}
