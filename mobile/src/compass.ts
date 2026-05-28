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

export function headingFromMagnetometer(vector: MagneticVector): number {
  return Math.round(normalizeDegrees((Math.atan2(vector.y, vector.x) * 180) / Math.PI));
}

export function formatHeading(degrees: number): string {
  const normalized = normalizeDegrees(degrees);
  return `${Math.round(normalized)} ${cardinalDirection(normalized)}`;
}

export function magneticStrength(vector: MagneticVector): number {
  const strength = Math.sqrt(vector.x ** 2 + vector.y ** 2 + vector.z ** 2);
  return Math.round(strength * 10) / 10;
}
