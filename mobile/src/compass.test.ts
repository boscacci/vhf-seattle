import { describe, expect, it } from "vitest";

import {
  AUTH_METHODS,
  COMPASS_NEEDLE_RESPONSE_MS,
  COMPASS_NORTH_NEEDLE_ROTATION_DEGREES,
  COMPASS_SENSOR_INTERVAL_MS,
  COMPASS_UI_REFRESH_INTERVAL_MS,
  cardinalDirection,
  clampedCompassGimbalTilt,
  compassBodyRotationForHeading,
  compassBodyRotationOutputRange,
  formatHeading,
  headingFromDeviceMotionRotation,
  headingFromMagnetometer,
  magneticStrength,
  nearestCompassHeading,
  normalizeDegrees,
  preciseHeadingFromMagnetometer,
  shortestCompassDelta,
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

  it("keeps sub-degree magnetometer headings for smooth animation", () => {
    expect(preciseHeadingFromMagnetometer({ x: 10, y: 1, z: 0 })).toBeCloseTo(5.7106, 4);
  });

  it("derives heading from native fused motion yaw", () => {
    expect(headingFromDeviceMotionRotation({ alpha: 0 })).toBe(0);
    expect(headingFromDeviceMotionRotation({ alpha: -Math.PI / 2 })).toBe(90);
    expect(headingFromDeviceMotionRotation({ alpha: Math.PI / 2 })).toBe(270);
  });

  it("clamps native pitch and roll into deliberate gimbal tilt", () => {
    expect(clampedCompassGimbalTilt({ alpha: 0, beta: Math.PI, gamma: -Math.PI })).toEqual({
      pitchDegrees: 16,
      rollDegrees: -16,
    });
    expect(clampedCompassGimbalTilt({ alpha: 0, beta: Math.PI / 12, gamma: Math.PI / 18 })).toEqual({
      pitchDegrees: 15,
      rollDegrees: 10,
    });
  });

  it("rotates through the shortest compass path across north", () => {
    expect(shortestCompassDelta(350, 10)).toBe(20);
    expect(shortestCompassDelta(10, 350)).toBe(-20);
    expect(nearestCompassHeading(350, 10)).toBe(370);
    expect(nearestCompassHeading(725, 2)).toBe(722);
  });

  it("keeps the north needle fixed while the compass body rotates under it", () => {
    expect(COMPASS_NORTH_NEEDLE_ROTATION_DEGREES).toBe(0);
    expect(compassBodyRotationForHeading(64)).toBe(-64);
    expect(compassBodyRotationForHeading(370)).toBe(-370);
    expect(compassBodyRotationOutputRange(36000)).toEqual(["36000deg", "-36000deg"]);
  });

  it("samples quickly enough for responsive phone rotation", () => {
    expect(COMPASS_SENSOR_INTERVAL_MS).toBeLessThanOrEqual(20);
    expect(COMPASS_UI_REFRESH_INTERVAL_MS).toBeLessThanOrEqual(16);
    expect(COMPASS_NEEDLE_RESPONSE_MS).toBe(0);
  });

  it("formats readable headings", () => {
    expect(formatHeading(267.6)).toBe("268 W");
    expect(formatHeading(359.6)).toBe("0 N");
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
