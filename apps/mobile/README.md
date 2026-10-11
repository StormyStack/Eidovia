# Eidovia — Mobile App

React Native / Expo app (SDK 57, TypeScript). Talks to the backend API Gateway on port `8000`.

---

## Prerequisites

- **Node.js**: 18+ installed on your PC.
- **Client App**: Install **Expo Go** (SDK 57) on your physical smartphone.
- **Network**: Phone and PC must be on the **same Wi-Fi network**.
- **Backend**: API Gateway running in Docker on port `8000`.

---

## Configuration

The app reads environment variables from `apps/mobile/.env`.

- **Current active IP**: `10.14.5.133`
- Configured in `apps/mobile/.env`:
  ```env
  EXPO_PUBLIC_API_URL=http://10.14.5.133:8000
  ```

*(If using an Android emulator on the same PC, change to `http://10.0.2.2:8000`)*

---

## Start

From `apps/mobile/`:

```powershell
cd apps\mobile
npm install

$env:REACT_NATIVE_PACKAGER_HOSTNAME = "10.14.5.133"
npx expo start --go --clear
```

Scan the QR code with **Expo Go** on your phone (same Wi-Fi as PC).
