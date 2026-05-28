export type MagneticVector = {
  x: number;
  y: number;
  z: number;
};

export type AuthMethod = {
  id: "google" | "sms_otp" | "passkey";
  label: string;
  caption: string;
};

const CARDINALS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"] as const;

export const COMPASS_SENSOR_INTERVAL_MS = 16;
export const COMPASS_ROTATION_RANGE_DEGREES = 36000;

export const AUTH_METHODS: AuthMethod[] = [
  {
    id: "google",
    label: "Google",
    caption: "Federated",
  },
  {
    id: "sms_otp",
    label: "Phone OTP",
    caption: "Passwordless",
  },
  {
    id: "passkey",
    label: "Passkey",
    caption: "Device-bound",
  },
];

export function normalizeDegrees(value: number): number {
  const normalized = value % 360;
  return normalized < 0 ? normalized + 360 : normalized;
}

export function cardinalDirection(degrees: number): string {
  const index = Math.round(normalizeDegrees(degrees) / 45) % CARDINALS.length;
  return CARDINALS[index];
}

export function preciseHeadingFromMagnetometer(vector: MagneticVector): number {
  return normalizeDegrees((Math.atan2(vector.y, vector.x) * 180) / Math.PI);
}

export function headingFromMagnetometer(vector: MagneticVector): number {
  return Math.round(preciseHeadingFromMagnetometer(vector));
}

export function shortestCompassDelta(fromDegrees: number, toDegrees: number): number {
  const delta = normalizeDegrees(toDegrees - fromDegrees + 180) - 180;
  return delta === -180 ? 180 : delta;
}

export function nearestCompassHeading(currentDegrees: number, targetDegrees: number): number {
  return currentDegrees + shortestCompassDelta(currentDegrees, targetDegrees);
}

export function formatHeading(degrees: number): string {
  const normalized = normalizeDegrees(degrees);
  return `${Math.round(normalized)} ${cardinalDirection(normalized)}`;
}

export function magneticStrength(vector: MagneticVector): number {
  const strength = Math.sqrt(vector.x ** 2 + vector.y ** 2 + vector.z ** 2);
  return Math.round(strength * 10) / 10;
}
