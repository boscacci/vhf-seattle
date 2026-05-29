import { describe, expect, it } from "vitest";

import {
  DEFAULT_APPROVED_EMAIL,
  SUPER_ADMIN_GROUP,
  authorizeCognitoClaims,
  cognitoDiscovery,
  cognitoLogoutUrl,
  decodeJwtClaims,
  readCognitoAuthConfig,
} from "./auth";

const toBase64Url = (value: unknown) =>
  globalThis
    .btoa(JSON.stringify(value))
    .replaceAll("+", "-")
    .replaceAll("/", "_")
    .replace(/=+$/, "");

describe("Cognito auth config", () => {
  it("stays disabled until the public Cognito app config exists", () => {
    expect(readCognitoAuthConfig({})).toBeNull();
  });

  it("normalizes public Cognito config from environment", () => {
    expect(
      readCognitoAuthConfig({
        EXPO_PUBLIC_COGNITO_CLIENT_ID: "abc123",
        EXPO_PUBLIC_COGNITO_DOMAIN: "talkingboats-dev.auth.us-west-2.amazoncognito.com/",
      }),
    ).toEqual({
      allowedEmail: DEFAULT_APPROVED_EMAIL,
      clientId: "abc123",
      domain: "https://talkingboats-dev.auth.us-west-2.amazoncognito.com",
      redirectUri: undefined,
    });
  });

  it("builds hosted login endpoints without embedding secrets", () => {
    const config = {
      allowedEmail: DEFAULT_APPROVED_EMAIL,
      clientId: "client-public-id",
      domain: "https://auth.example.com",
    };

    expect(cognitoDiscovery(config)).toEqual({
      authorizationEndpoint: "https://auth.example.com/oauth2/authorize",
      revocationEndpoint: "https://auth.example.com/oauth2/revoke",
      tokenEndpoint: "https://auth.example.com/oauth2/token",
    });
    expect(cognitoLogoutUrl(config, "elliottbayvhf://auth/callback")).toBe(
      "https://auth.example.com/logout?client_id=client-public-id&logout_uri=elliottbayvhf%3A%2F%2Fauth%2Fcallback",
    );
  });
});

describe("Cognito authorization rules", () => {
  it("accepts only Rob as super admin", () => {
    expect(
      authorizeCognitoClaims(
        {
          "cognito:groups": [SUPER_ADMIN_GROUP],
          email: "Cinemarob1@gmail.com",
        },
        { allowedEmail: DEFAULT_APPROVED_EMAIL },
      ),
    ).toEqual({
      email: DEFAULT_APPROVED_EMAIL,
      groups: [SUPER_ADMIN_GROUP],
      isSuperAdmin: true,
      ok: true,
    });
  });

  it("rejects any other Cognito user", () => {
    expect(
      authorizeCognitoClaims(
        {
          "cognito:groups": [SUPER_ADMIN_GROUP],
          email: "somebody@example.com",
        },
        { allowedEmail: DEFAULT_APPROVED_EMAIL },
      ).ok,
    ).toBe(false);
  });

  it("rejects Rob without the super-admin Cognito group", () => {
    expect(
      authorizeCognitoClaims(
        {
          "cognito:groups": [],
          email: DEFAULT_APPROVED_EMAIL,
        },
        { allowedEmail: DEFAULT_APPROVED_EMAIL },
      ).ok,
    ).toBe(false);
  });

  it("accepts Rob from the Google Cognito identity provider", () => {
    expect(
      authorizeCognitoClaims(
        {
          email: DEFAULT_APPROVED_EMAIL,
          identities: [
            {
              providerName: "Google",
              providerType: "Google",
              userId: "google-subject",
            },
          ],
        },
        { allowedEmail: DEFAULT_APPROVED_EMAIL },
      ),
    ).toEqual({
      email: DEFAULT_APPROVED_EMAIL,
      groups: [SUPER_ADMIN_GROUP],
      isSuperAdmin: true,
      ok: true,
    });
  });

  it("decodes Cognito JWT claims", () => {
    const payload = toBase64Url({
      "cognito:groups": [SUPER_ADMIN_GROUP],
      email: DEFAULT_APPROVED_EMAIL,
    });

    expect(decodeJwtClaims(`ignored.${payload}.ignored`)).toEqual({
      "cognito:groups": [SUPER_ADMIN_GROUP],
      email: DEFAULT_APPROVED_EMAIL,
    });
  });
});
