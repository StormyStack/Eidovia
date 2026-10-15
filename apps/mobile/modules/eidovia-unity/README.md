# eidovia-unity

Runs the DNA AR Unity game (`C:\Users\Sudipto\AR Game`) inside the Eidovia Expo app, using
*Unity as a Library* on Android. Used by `src/screens/ARGameScreen.tsx`.

```
 Expo app (React Native)                          Unity game (AR Game project)
 ARGameScreen ── <UnityView/> ──┐                 XR Origin
                                │ native view      ├─ MobileBridge   (messages with the app)
 UnityBridge.send(json) ────────┼──────────────▶   └─ LevelManager   (DNA journey)
 onMessage(json) ◀──────────────┘  UnityBridge.kt ◀── MobileBridge.Send
```

## Build (Android) — one app

The result is **one APK**: the Eidovia Expo app with the Unity game inside. The Unity library has no
launcher activity of its own (the export removes it), so there is only one icon on the phone.

1. **Unity** (AR Game project, build target Android): **Eidovia → Export for Mobile App**.
   It sets the Player Settings Unity as a Library needs (Activity entry point, IL2CPP, ARMv7 + ARM64) and exports
   `unityLibrary` to `apps/mobile/unity/builds/android`.
2. **Unity: Eidovia → Build Mobile App (APK)**, or in `apps/mobile`:
   ```powershell
   powershell -ExecutionPolicy Bypass -File scripts\build-android.ps1            # release APK
   powershell -ExecutionPolicy Bypass -File scripts\build-android.ps1 -Variant debug -Install
   ```
   The script uses the JDK and Android SDK that ship with Unity (no Android Studio needed), runs
   `expo prebuild --clean` and Gradle, and writes `apps/mobile/dist/Eidovia-<variant>.apk`
   (log: `dist/build-android.log`). It leaves `package.json` unchanged.
3. A **release** APK contains the JavaScript bundle and runs on its own. A **debug** APK loads JavaScript
   from Metro: run `npx expo start` on the PC (phone on the same Wi-Fi or USB). Re-run step 1 only when
   the Unity game changes; step 2 when native code or `app.json` changes.

`npx expo run:android --device` also works once `JAVA_HOME` and `ANDROID_HOME` point at Unity's
`...\Editor\Data\PlaybackEngines\AndroidPlayer\OpenJDK` and `...\SDK`.

The config plugin (`plugin/withEidoviaUnity.js`) links `unityLibrary` into the generated `android/`
project: settings.gradle includes, a flatDir repo for Unity's .aar files, Unity's `unity.*` Gradle
properties, Unity's NDK and build-tools for every module, Unity's noCompress list, minSdk 29,
the same CPU types as the Unity export (armeabi-v7a + arm64-v8a), legacy native-lib packaging and the `game_view_content_description` string. With
Only with `{ "cleartextHttp": true }` in app.json may the app call a LAN gateway over plain http (off: the app uses the https ngrok address).

The AR screen asks for the camera permission before Unity starts.

## Messages

App → Unity (`UnityBridge.send`, delivered to `XR Origin.OnHostMessage`, queued until Unity is ready):

| type | fields |
|---|---|
| `init` | `moduleId`, `sceneName` |
| `restart` | – |
| `wallet` | `total`, `added` (wildcards from the server wallet; `added` > 0 plays the gift animation) |

Unity → App (`onMessage`):

| type | fields |
|---|---|
| `ready` | – |
| `progress` | `stage`, `stageCount`, `found`, `required`, `wildcards` |
| `part_discovered` | `part`, `stage` |
| `stage_completed` | `stage`, `skipped` |
| `journey_completed` | – |
| `mode` | `ar` (false = 3D mode, no ARCore) |
| `wildcard_used` | `mode` (`skip` 1 card / `jump` 2 cards), `from`, `to`, `cost`, `left` |
| `previous_used` | `from`, `to` (free Back button, once per 30 s) |
| `wildcard_earned` | `stage` |

The game makes no network calls. Anything that should reach the backend (progress, AI) goes
through these messages and is handled by the app.

Only one `<UnityView/>` can be on screen; Unity keeps running (paused) when the screen closes, so
reopening it is instant.
