export type MagneticVector = {
  x: number;
  y: number;
  z: number;
};

export type DeviceMotionRotation = {
  alpha: number;
  beta?: number;
  gamma?: number;
};

export type AuthMethod = {
  id: "google" | "sms_otp" | "passkey";
  label: string;
  caption: string;
};

const CARDINALS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"] as const;

export const COMPASS_SENSOR_INTERVAL_MS = 16;
export const COMPASS_UI_REFRESH_INTERVAL_MS = 16;
export const COMPASS_NEEDLE_RESPONSE_MS = 0;
export const COMPASS_ROTATION_RANGE_DEGREES = 36000;
export const COMPASS_GIMBAL_MAX_TILT_DEGREES = 16;

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
  const positive = normalized < 0 ? normalized + 360 : normalized;
  return Object.is(positive, -0) ? 0 : positive;
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

export function headingFromDeviceMotionRotation(rotation: DeviceMotionRotation): number {
  return normalizeDegrees((-rotation.alpha * 180) / Math.PI);
}

export function clampedCompassGimbalTilt(rotation: DeviceMotionRotation): {
  pitchDegrees: number;
  rollDegrees: number;
} {
  return {
    pitchDegrees: clampTilt(radiansToDegrees(rotation.beta ?? 0)),
    rollDegrees: clampTilt(radiansToDegrees(rotation.gamma ?? 0)),
  };
}

function radiansToDegrees(value: number): number {
  return (value * 180) / Math.PI;
}

function clampTilt(value: number): number {
  return Math.max(-COMPASS_GIMBAL_MAX_TILT_DEGREES, Math.min(COMPASS_GIMBAL_MAX_TILT_DEGREES, Math.round(value)));
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
