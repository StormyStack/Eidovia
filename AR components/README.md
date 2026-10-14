# AR components: DNA AR game (Unity)

This is the Unity project for the DNA AR game. The game runs **inside** the Eidovia mobile app ("Unity as a Library").
It is not a separate app. Unity exports it as an Android library into `apps/mobile/unity/builds/android`,
and the build script then puts it into the single Eidovia APK.

- Unity **6000.3.25f1** with the Android module (IL2CPP, ARM64)
- AR Foundation / ARCore 6.3. AR is optional: phones without ARCore get a 3D mode.
- Scene: `Assets/Scenes/Root_ARPersistent.unity`

## Contents

| Path | What it is |
|---|---|
| `Assets/Scripts/LevelManager.cs` | the 5-level DNA journey: parts to discover, level flow, HUD |
| `Assets/Scripts/LevelManager.Power.cs` | wildcard power-ups (skip = 1 card, jump to any level = 2 cards, golden card animation) and the Back button (once every 30 s) |
| `Assets/Scripts/ARModelSpawner.cs`, `ARSupportFallback.cs` | placing the model in AR, 3D mode on phones without ARCore |
| `Assets/Scripts/ARInteractable.cs`, `Feel/` | touch, spring motion and the "living" molecules |
| `Assets/Scripts/ComponentPicker.cs`, `ComponentLabel.cs`, `TouchInteractionManager.cs` | tapping and naming the DNA parts |
| `Assets/Scripts/Bridge/MobileBridge.cs` | messages between the game and the React Native app (JSON both ways) |
| `Assets/Editor/EidoviaMobileExport.cs` | menus **Eidovia > Export for Mobile App** and **Eidovia > Build Mobile App (APK)** |
| `Assets/Models`, `Assets/Prefabs` | the DNA models (glTF) and one prefab per level |
| `Packages`, `ProjectSettings` | Unity packages and project settings |

The game makes no network calls and contains no AI code. Everything that has to reach the backend
(progress, wildcard use, earned cards, the Back button) goes through `MobileBridge` to the app,
and the app talks to the gateway. The wildcard count belongs to the server (one wallet per learner):
the app sends the total to the game with the `wallet` message.

### Messages

App → game (`UnitySendMessage("XR Origin", "OnHostMessage", json)`):
`init`, `restart`, `wallet {total, added}`

Game → app (`expo.modules.eidoviaunity.UnityBridge.onUnityMessage`):
`ready`, `progress`, `part_discovered`, `stage_completed`, `journey_completed`, `mode {ar}`,
`wildcard_used {mode, from, to, cost, left}`, `previous_used {from, to}`, `wildcard_earned {stage}`

## Building the app from this repo

1. Open `AR components` in Unity Hub with Unity 6000.3.25f1 and Android Build Support installed.
   The first import takes a few minutes. Set the build target to Android (File > Build Profiles > Android > Switch Platform).
2. Run **Eidovia > Export for Mobile App**. This writes `apps/mobile/unity/builds/android`, which is git-ignored.
3. Run **Eidovia > Build Mobile App (APK)**, or from `apps/mobile`:

   ```
   powershell -ExecutionPolicy Bypass -File scripts\build-android.ps1 -Install
   ```

   The APK is written to `apps/mobile/dist/Eidovia-release.apk` and the build log to `apps/mobile/dist/build-android.log`.

Before step 3, set `EXPO_PUBLIC_API_URL` in `apps/mobile/.env` to the gateway URL (for example the ngrok domain).
The script uses the JDK and Android SDK that come with Unity. Gradle downloads the NDK that React Native needs,
so you don't need Android Studio.
