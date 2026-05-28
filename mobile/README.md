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

The current managed-login path supports:

- Google federation
- SMS OTP passwordless sign-in
- Passkeys/WebAuthn

Only Cognito local password sign-in is enabled in dev until the Google and SMS
provider credentials are added securely outside git.
