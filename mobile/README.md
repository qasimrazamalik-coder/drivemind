# DriveMind for Android

The phone companion for DriveMind. It connects to DriveMind on your PC over your home Wi-Fi.

- **Home**: drive health ring, free space, a fill forecast, top fixes and alerts. A **Tidy now** button runs only what your settings say Yes to.
- **Review**: changes your PC proposed. Tick them, then approve and apply, reject, or undo a whole plan.
- **Cleaner**: a Yes / Ask / No switch for every cache, plus "Review a cache clean" and "Find temporary junk".
- **Settings**: Safe / Balanced / Autopilot mode and every switch. Changes apply on the PC straight away.
- **Search**: find a file on the PC by what is inside it, its type and its month or year.
- **Alerts**: new PC alerts (for example "C: is 90% full" or "Disk check: needs attention") arrive as phone notifications. While the app is closed, Android checks about every 15 minutes, when the phone is on the same Wi-Fi and has battery.

## Pair the phone

1. On the PC, run DriveMind (`scripts\DriveMind.bat`), then open **Settings > Phone > Pair a phone**.
2. In the app, tap **Find my PC**, pick your PC and type the 6-digit code it shows. The code works once, for 5 minutes.
   No luck finding it (some routers block devices from seeing each other)? Tap **Scan code** instead, or type the long code under "Typing it by hand instead?" on the PC.
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
src/app/pair.tsx             Find my PC + 6-digit code / QR scan / typed code / drivemind://pair deep link
src/app/(tabs)/              Home, Review, Search, Ask, Cleaner, Settings
src/app/plan/[id].tsx        review one plan
src/components/              UI kit (Card, Btn, Seg, Ring, Pill) and PlanView
src/lib/api.ts               typed client for the PC's /m API
src/lib/conn.tsx             saved connection, live sync (long-polls /m/events), data hook with offline copy
src/lib/alerts.ts            local notifications for PC alerts
src/lib/background.ts        background alert check (expo-background-task)
```

## Live sync and offline

While the app is open it keeps one request waiting at the PC (`/m/events`). The PC answers the moment something changes, and the screens showing that data reload, typically in well under a second. Each screen also keeps its last answer on the phone; when the PC can't be reached, the app shows that copy with "Offline · showing what your PC said …".

## Not yet

- Instant alerts while the app is closed. Today the background check runs about every 15 minutes; instant alerts need push through Firebase Cloud Messaging (FCM).
- Access away from home Wi-Fi. That needs a relay or a VPN such as Tailscale.
