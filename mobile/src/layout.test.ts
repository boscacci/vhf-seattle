import { describe, expect, it } from "vitest";

import { topChromeGutter } from "./layout";

describe("mobile layout helpers", () => {
  it("reserves a deliberate Android gutter around the system status bar", () => {
    expect(topChromeGutter("android", 24)).toBe(44);
    expect(topChromeGutter("android", 48)).toBe(60);
  });

  it("falls back when Android does not report a status bar height", () => {
    expect(topChromeGutter("android", undefined)).toBe(44);
    expect(topChromeGutter("android", 0)).toBe(44);
  });

  it("leaves non-Android safe-area handling to the platform", () => {
    expect(topChromeGutter("ios", 54)).toBe(0);
    expect(topChromeGutter("web", 24)).toBe(0);
  });
});
