import { describe, expect, it } from "vitest";

import {
  AUTH_METHODS,
  cardinalDirection,
  formatHeading,
  headingFromMagnetometer,
  magneticStrength,
  normalizeDegrees,
} from "./compass";

describe("compass helpers", () => {
  it("normalizes degrees into a compass circle", () => {
    expect(normalizeDegrees(-10)).toBe(350);
    expect(normalizeDegrees(370)).toBe(10);
    expect(normalizeDegrees(720)).toBe(0);
  });

  it("maps heading degrees to cardinal directions", () => {
    expect(cardinalDirection(0)).toBe("N");
    expect(cardinalDirection(44)).toBe("NE");
    expect(cardinalDirection(181)).toBe("S");
    expect(cardinalDirection(315)).toBe("NW");
  });

  it("derives a heading from magnetometer x and y readings", () => {
    expect(headingFromMagnetometer({ x: 0, y: 1, z: 0 })).toBe(90);
    expect(headingFromMagnetometer({ x: -1, y: 0, z: 0 })).toBe(180);
  });

  it("formats readable headings", () => {
    expect(formatHeading(267.6)).toBe("268 W");
  });

  it("measures magnetic vector strength", () => {
    expect(magneticStrength({ x: 3, y: 4, z: 12 })).toBe(13);
  });
});

describe("auth methods", () => {
  it("keeps the v0 login options on managed providers", () => {
    expect(AUTH_METHODS.map((method) => method.id)).toEqual([
      "google",
      "sms_otp",
      "passkey",
    ]);
  });
});
