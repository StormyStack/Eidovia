# EduAR-AI Mobile (`apps/mobile`)

React Native app for EduAR-AI, built with Expo SDK 57.
Sprint 1 scope: **Sign Up, Login and Home**, plus a placeholder AR screen.

## Stack

- **Expo SDK 57**, React Native **0.86** (New Architecture), React 19.2, TypeScript (strict)
- React Navigation 7 native stack
- Axios, Zustand 5, `expo-secure-store`, AsyncStorage

## Structure

```
apps/mobile/
├── index.ts                  Registers src/App
├── app.json                  Expo config (scheme "eduarai", plugins)
├── .env.example              EXPO_PUBLIC_API_URL template
├── jest.setup.ts             Test mocks (SecureStore, AsyncStorage, safe-area)
└── src/
    ├── App.tsx               Root navigation: splash → auth | app stack
    ├── config.ts             Reads + validates EXPO_PUBLIC_API_URL
    ├── theme.ts              Shared theme: colours, spacing, typography, branding
    ├── navigation/types.ts   Route names + param types
    ├── services/
    │   ├── ApiClient.ts      Axios client, Bearer injection, 401 → logout
    │   ├── AuthService.ts    login/register/getToken/getUserId/logout
    │   └── types.ts          Contract types
    ├── store/authStore.ts    Zustand: session state, restoreSession()
    ├── screens/              Login, SignUp, Home, ARGame (placeholder), Splash
    ├── components/           TextField, Button, Banner, StateView, ModuleCard, etc.
    ├── utils/validation.ts   Form rules (mirror the gateway's)
    └── test-utils/           Fake HTTP adapter, storage helpers (tests only)
```

## How It Works

- **Startup**: `App.tsx` calls `authStore.restoreSession()` and shows a splash screen.
  A saved, unexpired token opens **Home** (no network wait — works offline).
  In the background, `GET /api/users/{id}/profile` refreshes the username.
- **Login / Sign Up**: Client-side validation first (same rules as the server), then API call.
  Server field errors appear under their fields. Network/timeout errors show in a banner.
- **Home**: Greets by name, lists modules from `GET /api/modules`.
  Handles loading, empty, error + retry, and pull-to-refresh states.
  Tapping a module fetches its config and opens the AR screen.
- **Any 401**: Clears stored session and switches to Login automatically.
- **Storage**: Token in **SecureStore** (Keystore/Keychain). User ID and profile in AsyncStorage.

## Run on Your Phone (Expo Go)

### Prerequisites

1. Gateway running and reachable on your Wi-Fi
   (see [`apps/gateway/README.md`](../gateway/README.md))
2. PC Wi-Fi set to **Private** (Settings → Network → Wi-Fi)
3. Phone on the **same Wi-Fi**, Expo Go updated (SDK 57)

### Steps

```powershell
cd apps\mobile
npm install                     # first time only
copy .env.example .env          # set EXPO_PUBLIC_API_URL=http://<PC-IP>:8000
$env:REACT_NATIVE_PACKAGER_HOSTNAME = "<PC-IP>"
npx expo start --go --clear     # scan QR code with Expo Go
```

> **`--go`** is needed because `expo-dev-client` is installed; without it, Expo targets a dev build.
>
> **`REACT_NATIVE_PACKAGER_HOSTNAME`** prevents Expo from advertising a virtual adapter IP
> (e.g. VirtualBox `192.168.56.1`) in the QR code.

### `EXPO_PUBLIC_API_URL` Cheat Sheet

| Where the app runs | Value |
|---|---|
| Physical phone (same Wi-Fi) | `http://<PC-LAN-IP>:8000` |
| Android emulator on this PC | `http://10.0.2.2:8000` |
| iOS simulator (macOS) | `http://localhost:8000` |

> Restart Metro with `npx expo start --clear` after editing `.env` — the value is baked in at
> bundle time.

## Tests

```powershell
npm test                          # all unit + screen + navigation tests
npm test -- --coverage            # + coverage (threshold: ≥ 80% on src/services/)
npx tsc --noEmit                  # typecheck
npx expo-doctor                   # SDK/dependency health
```

| Suite | Covers |
|---|---|
| `services/__tests__/ApiClient` | Bearer injection, 401 → logout, error mapping, timeout |
| `services/__tests__/AuthService` | Token persistence (SecureStore), restart survival, logout purge |
| `store/__tests__/authStore` | restoreSession, login/register/logout, 401 end-to-end |
| `screens/__tests__/*` | Every screen state: validation, loading, API errors, retry, refresh |
| `__tests__/App` | Full navigation flows through the real stack |

### Live Integration Tests

Run against a real gateway (skipped by default):

```powershell
$env:GATEWAY_E2E_URL = "http://127.0.0.1:8000"
npx jest gateway.integration app.gateway.e2e
```

## Theming

Everything visual comes from `src/theme.ts`: `palette`, `spacing`, `radius`, `typography`, `shadow`,
and `brand`. To rebrand, change the palette and set `brand.logo = require('../assets/logo.png')`.

## Known Notes

- **`npm audit` (10 moderate)**: All from an old `uuid` in Expo's iOS build tooling. Not in the app bundle.
- **Placeholder identifiers**: `com.eduarai.mobile` — change before first EAS build.
- **No token refresh**: When the 7-day token expires, the user logs in again.
- **Development build (Sprint 2)**: Unity needs a dev build (not Expo Go). Plan: EAS Build.

## Pending Team Decisions

- **Unity library**: `@azesmway/react-native-unity` (not installed yet)
- **Module config `name` field**: Unity reads it but the API doesn't return it
- **Scene naming**: Unity scenes use cell biology names; AI curriculum uses DNA names
