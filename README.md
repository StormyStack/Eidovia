<div align="center">

# Eidovia

**Learn biology in augmented reality, with an AI tutor that adapts to you.**

[![Download APK](https://img.shields.io/badge/Download-Android%20APK-3DDC84?style=for-the-badge&logo=android&logoColor=white)](https://github.com/StormyStack/Thesis/raw/main/apps/mobile/dist/Eidovia-release.apk)

![Android](https://img.shields.io/badge/Android-10%2B-3DDC84?logo=android&logoColor=white)
![Version](https://img.shields.io/badge/version-1.0.0-2563EB)
![Expo](https://img.shields.io/badge/Expo-SDK%2057-000020?logo=expo&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-gateway-009688?logo=fastapi&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-4169E1?logo=postgresql&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white)

*Thesis project*

[Download](#download) · [Features](#features) · [Architecture](#architecture) · [Server setup](#server-setup) · [Admin Center](#admin-center) · [Build the app](#build-the-android-app) · [Troubleshooting](#troubleshooting)

</div>

---

## Download

| | |
|---|---|
| **File** | [`Eidovia-release.apk`](https://github.com/StormyStack/Thesis/raw/main/apps/mobile/dist/Eidovia-release.apk) (about 100 MB) |
| **Location in this repo** | [`apps/mobile/dist/`](apps/mobile/dist) |
| **Requires** | Android 10 or newer, any ARM phone (32-bit or 64-bit) |
| **AR** | Uses ARCore when the phone supports it. Other phones get a 3D mode instead. |

### Install on your phone

1. Open the **[download link](https://github.com/StormyStack/Thesis/raw/main/apps/mobile/dist/Eidovia-release.apk)** on your phone (or copy the APK to it).
2. Open the downloaded file. If Android asks, allow **Install unknown apps** for your browser or file manager.
3. If Google Play Protect shows a warning, tap **More details → Install anyway**. The app is not on Google Play, so Play Protect does not know it yet.
4. Open **Eidovia**, sign up, and choose **DNA** to start.

**Updating:** install the new APK over the old one. Your account and progress are kept.

---

## Features

- **DNA in AR.** Build the double helix in 5 levels: place the model in your room and discover its parts.
- **AI tutor.** Ask questions in a chat. Answers come from a local LLM (**Phi-4 mini on Ollama**) and adapt to your level.
- **DNA quiz.** 20 multiple-choice questions, scored on the server:
  - one attempt every 12 hours;
  - a **Force Attempt** for 3 wildcards;
  - or ask an admin for an early attempt.
- **Wildcards.** One wallet for the whole app: a daily gift, cards earned in the AR game, and cards given by an admin.
- **Progress dashboard.** Levels, play time, quiz scores (latest, best, average) and history.
- **Profile.** Name, level, age and gender, password change, forgot-password requests.
- **Admin Center.** Users, support requests, AR progress, quiz approvals, quiz logs and performance, service health and a live audit stream.

---

## Architecture

Everything on the server side runs with Docker Compose. The app talks only to the API Gateway.

| Service | Container | Port | URL |
|---|---|---|---|
| API Gateway | `eidovia_gateway` | `8080` | http://localhost:8080/docs |
| Admin Panel | `eidovia_admin` | `8090` | http://localhost:8090 |
| Ollama (Phi-4 mini) | `eidovia_ollama` | `11434` | http://localhost:11434 |
| PostgreSQL + pgvector | `eidovia_postgres` | `6543` | `localhost:6543` |
| Redis | `eidovia_redis` | `6379` | `localhost:6379` |
| Logger | `eidovia_logger` | – | – |

### Repository structure

```
Thesis/
├── apps/
│   ├── mobile/          React Native (Expo) app
│   │   └── dist/        the released APK (download link above)
│   └── admin/           Admin Center (FastAPI + dashboard)
├── services/
│   ├── gateway/         API Gateway (auth, AR progress, wildcards, quiz)
│   ├── ai/              AI service (RAG + Ollama) and the database migrations
│   └── logger/          audit log worker (Redis → PostgreSQL)
├── AR components/       Unity project of the DNA AR game
└── docker-compose.yml
```

Each part has its own README with details: [mobile app](apps/mobile/README.md), [AR game](AR%20components/README.md), [gateway](services/gateway/README.md), [AI service](services/ai/README.md).

---

## Server setup

### Requirements

- **Docker Desktop**
- **NVIDIA GPU** *(optional)*. Without one, delete the `deploy:` block under `ollama:` in `docker-compose.yml`.

Run all commands from the project root (`Thesis/`).

### 1. Create `.env`

```powershell
Copy-Item .env.example .env
```

Fill in `DB_PASSWORD`, `REDIS_PASSWORD`, `JWT_SECRET` and `SEED_USER_PASSWORD`.

### 2. Start the containers

```powershell
docker compose up -d --build
docker compose ps
```

### 3. Install Phi-4 mini (required for AI chat)

```powershell
docker exec eidovia_ollama ollama pull phi4-mini
docker exec eidovia_ollama ollama list
```

`phi4-mini` must appear in the list. You only pull it once, because it's saved in a Docker volume.

### 4. Seed the database

```powershell
docker exec -i eidovia_gateway python -m scripts.setup_db
```

### 5. Create an admin account

```powershell
docker exec -i eidovia_gateway python -m scripts.create_admin <username> <email> <password>
```

### Daily use

```powershell
# Start
docker compose up -d

# Stop (keeps all data)
docker compose stop

# After pulling new code: restart the services so they load it
docker compose restart gateway admin logger
```

> [!WARNING]
> Don't run `docker compose down -v`. It deletes the database and the Phi-4 mini model.

### Check that it works

```powershell
docker compose ps
Invoke-RestMethod http://localhost:8080/health
Invoke-RestMethod http://localhost:8090/health
docker exec eidovia_ollama ollama list
```

---

## Admin Center

Open **[http://localhost:8090](http://localhost:8090)**. It redirects to the dashboard at [http://localhost:8090/admin/dashboard](http://localhost:8090/admin/dashboard).

1. Make sure the containers are running (`docker compose up -d`).
2. Sign in with the username and password you created in setup step 5.
3. Click **Enter Admin Center**.

Only accounts with the admin role can sign in. To give an existing user the admin role, run setup step 5 again with their username.

---

## Build the Android app

Needs Node.js, the Android SDK and a JDK on Windows. From `apps/mobile`:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build-android.ps1
```

| Option | What it does |
|---|---|
| *(none)* | Signed release APK → `apps/mobile/dist/Eidovia-release.apk` |
| `-Install` | Also installs it on a phone connected with USB debugging |
| `-Bundle` | Also builds `Eidovia-release.aab` (for Google Play) |
| `-Clean` | Regenerates the native `android/` project from scratch |

The build log is saved as `apps/mobile/dist/build-android.log`. You only need to export from Unity again when the AR game itself changes (see the [AR game README](AR%20components/README.md)).

> [!IMPORTANT]
> The app is signed with the key in `apps/mobile/credentials/`. That folder is never committed. Keep a private backup: without the same key, phones can't install updates over the old app.

### Publish a new version

The APK is larger than GitHub's 100 MB limit for normal files, so it is stored with **[Git LFS](https://git-lfs.com)** (`.gitattributes`). The download link above always serves the latest committed APK.

1. Raise `version` in `apps/mobile/app.json` (and in the badge above).
2. Build the app (see above).
3. Commit and push the APK:

   ```powershell
   git lfs install                      # once per computer
   git add apps/mobile/dist/Eidovia-release.apk
   git commit -m "Release Eidovia 1.0.1"
   git push
   ```

---

## Troubleshooting

| Problem | Fix |
|---|---|
| Chat says "Port 11434 (Ollama) is being connected…" | Phi-4 mini isn't installed. Run setup step 3 |
| `Set DB_PASSWORD in .env` | Missing values in `.env`. See setup step 1 |
| `port 11434 ... only one usage` | The Windows Ollama app is running. Quit it |
| Admin Center tab is empty after an update | Run `docker compose restart admin` and reload the page |
| Phone: "App not installed" / "package conflicts" | An app with the same name but another signing key is installed. Uninstall it first |
| Phone: "Blocked by Play Protect" | Tap **More details → Install anyway** |
| `git push` fails: file is larger than 100 MB | Git LFS wasn't active when the APK was added. Run `git lfs install`, then `git rm --cached apps/mobile/dist/Eidovia-release.apk`, add and commit it again |
| See logs | `docker compose logs -f gateway` (or `ollama`, `admin`, `logger`, `postgres`) |
