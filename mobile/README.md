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

Use a managed identity provider rather than custom credentials. The current target is AWS Cognito with:

- Google federation
- SMS OTP passwordless sign-in
- Passkeys/WebAuthn as the third convenient secure path

Keep client IDs, pool IDs, and callback URLs out of git; wire them through environment-specific config once the dev auth resources exist.
