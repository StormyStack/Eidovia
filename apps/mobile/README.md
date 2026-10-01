# EduAR-AI Mobile (`apps/mobile`)

React Native host app for EduAR-AI, built by **team member #4, the React Native developer**.
Sprint 1 scope: **Sign Up, Login and Home**, plus a placeholder AR screen. The app talks to the API
Gateway (`apps/gateway`) using the contract in [`docs/api-auth-home.md`](../../docs/api-auth-home.md).

- **Stack:**
  - Expo **SDK 57**, React Native **0.86** (New Architecture), React 19.2, TypeScript (strict)
  - React Navigation 7 **native stack** (as the RN Dev Reference Document specifies; **not Expo Router**)
  - axios, zustand, `expo-secure-store`, AsyncStorage, `@expo/vector-icons`
- **Workflow:** dev-build ready (`expo-dev-client` installed, `app.json` prebuild-configured).
  Sprint 1 runs in **Expo Go**, because every dependency is bundled in Expo Go.

## Structure (PDF layout + a few helpers)

```
apps/mobile/
├── index.ts                  registers src/App
├── app.json                  name, scheme "eduarai", android.package / ios.bundleIdentifier, plugins
├── .env.example              EXPO_PUBLIC_API_URL template (copy to .env, which is gitignored)
├── jest.setup.ts             test mocks: SecureStore/AsyncStorage (persist across "restarts"), safe-area
└── src/
    ├── App.tsx               root navigation: splash → auth stack (Login, SignUp) | app stack (Home, ARGame)
    ├── config.ts             reads + validates EXPO_PUBLIC_API_URL; API timeout 5 s
    ├── theme.ts              THE shared theme: colours, spacing, typography, brand (name/logo)
    ├── navigation/types.ts   route names + params
    ├── services/
    │   ├── ApiClient.ts      axios client, Bearer injection, 401 → logout, ApiError, typed endpoints
    │   ├── AuthService.ts    login/register/getToken/getUserId/logout; token in SecureStore
    │   └── types.ts          contract types
    ├── store/authStore.ts    zustand: user_id, token, profile, isLoading, isAuthenticated, restoreSession()
    ├── screens/              LoginScreen, SignUpScreen, HomeScreen, ARGameScreen (placeholder), SplashScreen
    ├── components/           TextField, Button, Banner, StateView, ModuleCard, BrandHeader, ScreenContainer
    ├── utils/validation.ts   form rules (mirror the gateway's)
    └── test-utils/           fake HTTP adapter, storage helpers, screen render helper (tests only)
```

`android/` and `ios/` are **generated** by `npx expo prebuild` (Continuous Native Generation) and
gitignored. Configure native behaviour in `app.json` and config plugins, never by hand.

## How it works

- **Startup:**
  - `App.tsx` calls `authStore.restoreSession()` and shows the splash screen meanwhile.
  - A saved, unexpired token opens **Home**; there is no network wait, so it works offline.
  - In the background, `GET /api/users/{id}/profile` refreshes the username. If that returns 401,
    the app goes back to **Login** with a notice.
- **Login / Sign Up:**
  - Both screens validate on the device first, using the same rules as the server.
  - The submit button shows a spinner and is disabled while sending, so a double tap can't submit twice.
  - Server field errors appear under their fields (e.g. 409 "This username is already taken.").
    Wrong-password, network and timeout messages appear in a banner.
- **Home:**
  - Greets you by name and lists modules from `GET /api/modules`.
  - Handles loading, empty, error-with-Try-again and pull-to-refresh states.
  - Tapping a module calls `GET /api/modules/{id}/config` and opens `ARGameScreen` with that config.
- **Any 401** from a protected request clears the stored session (`AuthService.logout()`), and
  navigation switches to Login automatically.
- **Storage:**
  - The token is in **SecureStore** (Keystore/Keychain). This is a deliberate deviation from the PDF's
    AsyncStorage, for security. The key names and the `AuthService` API are unchanged.
  - `user_id` and the cached profile are in AsyncStorage.

## Run on your Android phone (Expo Go)

1. **Gateway running and reachable on your Wi-Fi.** See [`apps/gateway/README.md`](../gateway/README.md):
   `python -m scripts.dev_db start`, then `uvicorn ... --host 0.0.0.0 --port 8000`.
2. **PC network:**
   - Set your Wi-Fi network profile to **Private** (Settings → Network & internet → Wi-Fi).
     Windows Firewall blocks phones on Public networks.
   - Allow Node.js and Python on Private networks when asked.
3. **Phone:** same Wi-Fi as the PC (not a guest network); Expo Go updated (SDK 57).
4. **Config and start:**
   ```powershell
   cd F:\Thesis\Thesis-final\apps\mobile
   npm install                     # first time only
   copy .env.example .env          # set EXPO_PUBLIC_API_URL=http://<PC Wi-Fi IPv4>:8000  (ipconfig)
   $env:REACT_NATIVE_PACKAGER_HOSTNAME = "<PC Wi-Fi IPv4>"
   npx expo start --go --clear     # scan the QR code with Expo Go
   ```
   - `--go` is needed because `expo-dev-client` is installed; without it the CLI targets a development build.
   - `REACT_NATIVE_PACKAGER_HOSTNAME` stops Expo from advertising a virtual adapter's IP (e.g. VirtualBox
     `192.168.56.1`) in the QR code.
   - If the LAN still doesn't work, use `npx expo start --go --tunnel`. That only covers Metro; the gateway URL
     must still be reachable from the phone.

### `EXPO_PUBLIC_API_URL` cheat sheet
| Where the app runs | Value |
|---|---|
| Physical phone, same Wi-Fi | `http://<PC Wi-Fi IPv4>:8000` |
| Android emulator on this PC | `http://10.0.2.2:8000` |
| iOS simulator (macOS) | `http://localhost:8000` |

- **Restart after edits:** the value is baked in at bundle time, so restart with `npx expo start --clear`
  after editing `.env`. It is visible inside the app, so never put secrets in `EXPO_PUBLIC_*`.
- **Plain HTTP:**
  - Expo Go and debug development builds allow `http://` to your LAN.
  - Release builds block it on Android; production should use `https://`.

## Tests

```powershell
npm test                          # all unit + screen + navigation tests
npm test -- --coverage            # + coverage (threshold: >= 80% on src/services/)
npx tsc --noEmit                  # typecheck
npx expo-doctor                   # SDK/dependency health
```

| Suite | What it covers |
|---|---|
| `src/services/__tests__/ApiClient.test.ts` | Bearer injection, 401 → logout (and not for login), stale-token guard, error mapping, **real 5 s-style timeout with 0 unhandled rejections** |
| `src/services/__tests__/AuthService.test.ts` | token stored on login (SecureStore only), **survives restart**, **logout purges everything**, storage failures |
| `src/store/__tests__/authStore.test.ts` | restoreSession (valid / expired / offline / revoked), login/register/logout, 401 end-to-end |
| `src/screens/__tests__/*` | every screen state: validation, loading/disabled, API errors (401, 409, network, timeout), toggle, empty/error/retry/refresh, open module, logout confirm |
| `src/__tests__/App.test.tsx` | whole-app flows through the real React Navigation stack |
| `src/__tests__/*.e2e / *.integration` | **against a real gateway** (skipped unless `GATEWAY_E2E_URL` is set) |

Run the live suites against a running gateway:
```powershell
$env:GATEWAY_E2E_URL = "http://127.0.0.1:8000"; npx jest gateway.integration app.gateway.e2e
```

Last results (2026-10-01):
- **152 passed**; coverage on `src/services/` is **99.25% statements / 97% branches / 100% functions / 100% lines**, and 96.7% overall.
- The live suites passed **14/14**.

**Test-environment notes:**
- **RNTL v14:** `render`, `fireEvent` and `act` are async (`await` them).
- **Network in Jest:** `jest-expo` loads axios' browser build and stubs `fetch`, so the real-network tests use `xhr2` (dev-only).
- **Empty coverage table:** if the coverage table is ever empty, run `npx jest --clearCache` (stale Jest cache).

## Theming and branding

Everything visual comes from `src/theme.ts`: `palette`, `spacing`, `radius`, `typography`, `shadow`
and `brand`. To rebrand, change the palette and set `brand.logo = require('../assets/logo.png')`.
Every screen picks it up.

## Known notes

- **`npm audit` (10 moderate):** all from one advisory in an old `uuid` inside Expo's build-time iOS
  tooling (`xcode` package). It isn't in the app bundle. `npm audit fix --force` would break SDK alignment.
- **Placeholder identifiers:** `com.eduarai.mobile` (Android package / iOS bundle ID). Change it before the first EAS build if needed.
- **No token refresh endpoint yet.** When the 7-day token expires, the user logs in again.
- **Development build (Sprint 2):** the Unity module needs one, because it's native code that Expo Go doesn't include.
  The plan is EAS: `npx eas-cli@latest login`, then `npx eas-cli@latest build --profile development --platform android`.
  Step-by-step instructions will be given when Sprint 2 starts.

## Pending team decisions

- **Unity library (Sprint 2):**
  - The PDF's `react-native-unity-view` is unmaintained and doesn't support the New Architecture,
    which React Native 0.82+ requires.
  - The plan is `@azesmway/react-native-unity`. It isn't installed yet.
  - The Unity developer's `ReactNativeBridge.cs` must replace `UnityMessageManager.Instance.SendMessageToRN(json)`
    with that plugin's send-to-RN call.
  - `src/bridge/UnityBridge.ts` (PDF API: `handleUnityMessage`, `sendAdaptAction`, `sendModuleConfig`) comes with it.
- **Module config `name`:** Unity's `ModuleConfig` reads `name`, but the PDF config contract doesn't return it. The contract is kept as-is.
- **Scene naming:** Unity's scenes are cell biology (`GameScene_Cell*`, used by the gateway seed), while
  the AI curriculum uses DNA module names. The team should choose one.
- **Gateway items needing SE agreement:** listed at the end of [`docs/api-auth-home.md`](../../docs/api-auth-home.md).
