import { describe, expect, it } from "vitest";
import packageJson from "../package.json";

describe("Expo Go compatibility", () => {
  it("uses the current SDK line for quick phone testing", () => {
    expect(packageJson.dependencies.expo).toMatch(/^\^56\./);
  });

  it("keeps the xcode UUID override on the CommonJS-compatible fixed line", () => {
    expect(packageJson.overrides.xcode.uuid).toMatch(/^\^11\./);
  });

});
