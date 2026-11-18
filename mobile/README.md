# DriveMind for Android

The phone companion for DriveMind. It connects to DriveMind on your PC over your home Wi-Fi.

- **Home**: drive health ring, free space, a fill forecast, top fixes and alerts. A **Tidy now** button runs only what your settings say Yes to.
- **Review**: changes your PC proposed. Tick them, then approve and apply, reject, or undo a whole plan.
- **Cleaner**: a Yes / Ask / No switch for every cache, plus "Review a cache clean" and "Find temporary junk".
- **Settings**: Safe / Balanced / Autopilot mode and every switch. Changes apply on the PC straight away.
- **Alerts**: while the app is open, new PC alerts (for example "C: is 90% full") arrive as phone notifications.

## Pair the phone

1. On the PC, run DriveMind (`scripts\DriveMind.bat`), then open **Settings > Phone > Pair a phone**.
2. In the app, tap **Scan code**, or tap **Enter code** and type the code shown on the PC (`192.168.x.x:7878#…`).
3. The first time, Windows may ask to allow Python on the network. Choose **Private networks**.

Each phone gets its own secret token, and the PC stores only a hash of it. To remove a phone, use **Settings > Phone > Remove** on the PC. The PC dashboard itself is never reachable over Wi-Fi; only the token-protected `/m` phone API is.

## Run it

```bash
npm install
npx expo start          # scan the QR with Expo Go on your phone (same Wi-Fi)
```

## Build an APK / Play Store bundle

```bash
npx eas-cli@latest login
npm run build:apk                                  # installable APK (preview profile)
npx eas-cli@latest build -p android --profile production   # .aab for Google Play
```

Package name: `com.qasimrazamalik.drivemind`. Cleartext HTTP is enabled through `expo-build-properties`, because the phone talks to your PC on the local network.

## Code map

```text
src/app/_layout.tsx          stack + providers
src/app/pair.tsx             QR scan / typed code / drivemind://pair deep link
src/app/(tabs)/              Home, Review, Cleaner, Settings
src/app/plan/[id].tsx        review one plan
src/components/              UI kit (Card, Btn, Seg, Ring, Pill) and PlanView
src/lib/api.ts               typed client for the PC's /m API
src/lib/conn.tsx             saved connection + data hook
src/lib/alerts.ts            local notifications for PC alerts
```

## Not yet

- Alerts while the app is closed. That needs push through Firebase Cloud Messaging (FCM) or background tasks; today alerts arrive while the app is open.
- Access away from home Wi-Fi. That needs a relay or a VPN such as Tailscale.
