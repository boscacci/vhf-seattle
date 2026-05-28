declare const Buffer:
  | {
      from(input: string, encoding: string): { toString(encoding: string): string };
    }
  | undefined;

declare const process:
  | {
      env?: Record<string, string | undefined>;
    }
  | undefined;

export const DEFAULT_APPROVED_EMAIL = "cinemarob1@gmail.com";
export const SUPER_ADMIN_GROUP = "super-admins";

export type CognitoAuthConfig = {
  allowedEmail: string;
  clientId: string;
  domain: string;
  redirectUri?: string;
};

export type CognitoClaims = {
  email?: string;
  "cognito:groups"?: string[];
  identities?: Array<{
    providerName?: string;
    providerType?: string;
    userId?: string;
  }>;
};

export type AuthzResult =
  | {
      email: string;
      groups: string[];
      isSuperAdmin: true;
      ok: true;
    }
  | {
      reason: string;
      ok: false;
    };

export function readCognitoAuthConfig(
  env: Record<string, string | undefined> = process?.env ?? {},
): CognitoAuthConfig | null {
  const clientId = env.EXPO_PUBLIC_COGNITO_CLIENT_ID?.trim();
  const domain = normalizeCognitoDomain(env.EXPO_PUBLIC_COGNITO_DOMAIN);

  if (!clientId || !domain) {
    return null;
  }

  return {
    allowedEmail: (env.EXPO_PUBLIC_COGNITO_ALLOWED_EMAIL || DEFAULT_APPROVED_EMAIL)
      .trim()
      .toLowerCase(),
    clientId,
    domain,
    redirectUri: env.EXPO_PUBLIC_COGNITO_REDIRECT_URI?.trim() || undefined,
  };
}

export function normalizeCognitoDomain(value: string | undefined): string | null {
  const trimmed = value?.trim().replace(/\/+$/, "");
  if (!trimmed) {
    return null;
  }
  return trimmed.startsWith("https://") ? trimmed : `https://${trimmed}`;
}

export function cognitoDiscovery(config: CognitoAuthConfig) {
  return {
    authorizationEndpoint: `${config.domain}/oauth2/authorize`,
    revocationEndpoint: `${config.domain}/oauth2/revoke`,
    tokenEndpoint: `${config.domain}/oauth2/token`,
  };
}

export function cognitoLogoutUrl(config: CognitoAuthConfig, logoutUri: string): string {
  return `${config.domain}/logout?client_id=${encodeURIComponent(
    config.clientId,
  )}&logout_uri=${encodeURIComponent(logoutUri)}`;
}

export function decodeJwtClaims(token: string): CognitoClaims {
  const [, payload] = token.split(".");
  if (!payload) {
    throw new Error("Missing JWT payload");
  }

  return JSON.parse(decodeBase64Url(payload)) as CognitoClaims;
}

export function authorizeCognitoClaims(
  claims: CognitoClaims,
  config: Pick<CognitoAuthConfig, "allowedEmail">,
): AuthzResult {
  const email = claims.email?.trim().toLowerCase();
  if (!email || email !== config.allowedEmail) {
    return { ok: false, reason: "This Cognito user is not approved for Elliott Bay VHF." };
  }

  const groups = claims["cognito:groups"] ?? [];
  const isGoogleIdentity = (claims.identities ?? []).some(
    (identity) => identity.providerName === "Google" || identity.providerType === "Google",
  );
  if (!groups.includes(SUPER_ADMIN_GROUP) && !isGoogleIdentity) {
    return { ok: false, reason: "This Cognito user is missing super-admin access." };
  }

  return {
    email,
    groups: groups.includes(SUPER_ADMIN_GROUP) ? groups : [SUPER_ADMIN_GROUP],
    isSuperAdmin: true,
    ok: true,
  };
}

function decodeBase64Url(value: string): string {
  const base64 = value.replace(/-/g, "+").replace(/_/g, "/");
  const padded = base64.padEnd(Math.ceil(base64.length / 4) * 4, "=");

  if (typeof atob === "function") {
    return atob(padded);
  }
  if (typeof Buffer !== "undefined") {
    return Buffer.from(padded, "base64").toString("utf8");
  }
  throw new Error("No base64 decoder is available");
}
