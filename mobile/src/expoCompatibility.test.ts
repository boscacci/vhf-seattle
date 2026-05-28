import { describe, expect, it } from "vitest";
import packageJson from "../package.json";

describe("Expo Go compatibility", () => {
  it("uses the conservative SDK line for quick phone testing", () => {
    expect(packageJson.dependencies.expo).toMatch(/^~55\./);
  });
});
