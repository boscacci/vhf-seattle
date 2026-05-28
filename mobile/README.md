# Elliott Bay VHF Mobile

Expo React Native v0 for Android/iOS parity. This first build is intentionally small:

- Captain-hat identity mark drawn with `react-native-svg`
- Compass shell using `expo-sensors` magnetometer when available
- Managed login lanes staged for Google, phone OTP, and passkeys

## Run on Android Wirelessly

Install Expo Go on the phone, then run:

```bash
cd mobile
npm run start -- --lan
```

Scan the QR code with Expo Go while the phone and Mac are on the same network.

If LAN discovery is being fussy:

```bash
cd mobile
npm run start -- --tunnel
```

## Checks

```bash
cd mobile
npm test
npm run typecheck
```

## Auth Direction

Use AWS Cognito Hosted UI with OAuth authorization code + PKCE. Dev auth is
admin-created only: `cinemarob1@gmail.com` is provisioned into the
`super-admins` group, and the app rejects any token that does not match both the
approved email and group.

After applying the dev OpenTofu stack, write the local Expo config:

```bash
scripts/write_mobile_auth_env.sh
```

That creates `mobile/.env.local`, which is intentionally gitignored. For Expo Go
over the tailnet, the default redirect URI is:

```text
exp://100.125.120.39:8083/--/auth/callback
```

The intended dev sign-in path is Google federation through Cognito Hosted UI.
Create a Google OAuth web client, add the Cognito `/oauth2/idpresponse`
redirect URI, store the client credential JSON in AWS Secrets Manager as
`talkingboats/dev/google-oauth-client`, then run:

```bash
scripts/configure_dev_google_cognito_idp.sh
```

The script keeps the Google client secret out of git and local OpenTofu state,
then switches the dev mobile client to Google-only sign-in. Set
`TALKINGBOATS_GOOGLE_OAUTH_SECRET_ID` if you use a different AWS secret name.
The app still rejects every Cognito token except `cinemarob1@gmail.com`; a
verified Google identity for that address is treated as the super admin.

Future managed-login lanes:

- SMS OTP passwordless sign-in
- Passkeys/WebAuthn
