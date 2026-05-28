# Mobile Agent Notes

- Use Expo SDK 56 documentation for native modules before changing dependencies.
- Keep the v0 app Expo Go compatible unless a native development build is explicitly needed.
- Do not commit OAuth client secrets, Cognito IDs, signing keys, or device-specific build artifacts.
- Preserve Android/iOS parity: shared React Native code first, platform branches only when behavior truly differs.
