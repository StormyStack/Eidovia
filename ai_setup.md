
Confirm `.env` is not tracked:

```powershell
git ls-files .env
```

This must print nothing.

### 2. Start Docker services

```powershell
docker compose up -d
docker compose ps
```

You should see `eidovia_postgres`, `eidovia_redis`, and `eidovia_ollama`, all running.

### 3. Pull the Ollama models (first time only, about 2.5 GB)

```powershell
docker exec eidovia_ollama ollama pull phi4-mini
docker exec eidovia_ollama ollama pull all-minilm
docker exec eidovia_ollama ollama list
```

Models are stored in the `ollama_models` Docker volume, so you only pull once per machine.

### 4. Apply the database migrations

Run these once, in order. They use `IF NOT EXISTS`, so re-running is safe.

```powershell
Get-Content services\ai\migrations\001_schema.sql | docker exec -i eidovia_postgres psql -U appuser -d eidovia
Get-Content services\ai\migrations\002_events.sql | docker exec -i eidovia_postgres psql -U appuser -d eidovia
Get-Content services\ai\migrations\003_hoe_levels.sql | docker exec -i eidovia_postgres psql -U appuser -d eidovia
```

If `001` reports that tables already exist, that's fine.

### 5. Install Python dependencies (host)

```powershell
cd E:\Thesis
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r services\ai\requirements.txt
python -m pip install -r services\gateway\requirements.txt
```

The AI requirements include PyTorch (for the local embedder), which is large.

### 6. Load the curriculum

```powershell
cd E:\Thesis\services\ai
E:\Thesis\.venv\Scripts\python.exe -m scripts.load_curriculum
```

Expected final line: `Inserted 17 chunks. Per level: {1: 2, 2: 2, 3: 2, 4: 11}`.

Re-running replaces the chunks for `DNA_BIOLOGY_001`.

### 7. Seed the demo user

The seed script runs through the gateway's code on the host:

```powershell
cd E:\Thesis\services\gateway
E:\Thesis\.venv\Scripts\python.exe -m scripts.setup_db
```

---

## Daily start

Open three PowerShell windows.

**Window 1: Docker (once per boot)**

```powershell
cd E:\Thesis
docker compose up -d
```

**Window 2: AI service**

```powershell
cd E:\Thesis\services\ai
E:\Thesis\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8001
```

Leave it running. Wait for `Application startup complete`.

**Window 3: Gateway**

```powershell
cd E:\Thesis\services\gateway
E:\Thesis\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

`0.0.0.0` lets your phone reach it. Allow it through Windows Firewall on Private networks if asked.

**Mobile app (optional)**

```powershell
cd E:\Thesis\apps\mobile
npm install
npx expo start --go --clear
```

Set `EXPO_PUBLIC_API_URL=http://<your PC IP>:8000` in `apps\mobile\.env`. Find your IP with `ipconfig`.

### Stop

```powershell
docker compose stop
```

Press Ctrl+C in windows 2 and 3. This keeps all data.

Do not use `docker compose down -v`. It deletes the database and model volumes.

---

## Check that everything works

```powershell
Invoke-RestMethod http://localhost:8001/health
Invoke-RestMethod http://localhost:8000/health
docker exec eidovia_ollama ollama ps
```

The AI health output should show `rag_ready: True`, `embed_backend: local`, and `mock_llm: False`.

Test the depth cap:

```powershell
Invoke-RestMethod -Method Post -Uri http://localhost:8001/api/chat -ContentType "application/json" -Body '{"question":"What enzyme builds new DNA strands?","hoe_level":4}'
```

Expected: an answer naming DNA polymerase, with `retrieved` entries at Level 4. The first answer can take a minute while the model loads.

---

## GPU (optional, for faster answers)

The `ollama` service in `docker-compose.yml` reserves an NVIDIA GPU. It needs NVIDIA drivers and Docker Desktop GPU support. Without a GPU, remove the `deploy:` block under `ollama:` before running `docker compose up -d`.

Check the processor:

```powershell
docker exec eidovia_ollama ollama ps
```

`100% GPU` means GPU is in use. `100% CPU` means it isn't.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `port 11434 ... only one usage` | Quit the Windows Ollama app. Check with `Get-NetTCPConnection -LocalPort 11434 -State Listen` |
| `nslookup registry-1.docker.io` fails | DNS problem. Flush with `ipconfig /flushdns` or switch DNS to 8.8.8.8 |
| `password authentication failed` | `.env` password doesn't match the volume. Don't change it without resetting the database |
| `Required environment variable not set` | Missing value in `.env` |
| Chat returns raw chunks | `MOCK_LLM=True` in `.env`. Set it to `False` and restart the AI service |
| Chat says "temporarily unavailable" | Ollama container isn't running, or the model isn't pulled |
| `Could not find 'level' ...` or missing chunks | Re-run step 6 |

---

## Next steps

Work through these in order.

**Week 1: evidence**

1. **Write the question set.** 30 DNA questions, 6 to 8 per level. Save as `services/ai/scripts/questions_v1.json` before running the next comparison. Commit it.
2. **Check gold labels.** A second person verifies each label against the curriculum. Record agreement.
3. **Build the fixed-size baseline.** Load the old 500-character chunks into a separate table, so the flat comparison is fair.
4. **Run the three-condition comparison:**
   - Flat, sectioned chunks (no cap)
   - HOE-capped chunks
   - Flat, fixed-size chunks
5. **Rate depth fit.** 1 to 5 for each answer, with two raters on at least 10 answers. Report agreement.

**Week 2: decisions and write-up**

6. **Review the HOE mapping with your supervisor.** Confirm the four level definitions and which sub-sections belong where. Move "Natural Selection" out of Level 1 unless it's justified. Split Level 4 (11 of 17 chunks) so the cap has real steps.
7. **Re-run the evaluation** after any mapping change. Flush the cache first:
```powershell
   Invoke-RestMethod -Method Post -Uri http://localhost:8001/api/cache-flush
```
8. **Settle the "fine-tuned" wording with your supervisor.** Use "retrieval-grounded, prompted LLM" unless you fine-tune.
9. **Write the methods section.** Name the embedder as `all-MiniLM-L6-v2 (sentence-transformers)`. Describe the LLM as Phi-4 mini, prompted and retrieval-grounded.
10. **Write the limitations.** Pilot sample size, one curriculum, one mapping chosen by the authors, CPU or GPU timing differences, and no user study yet.

**Later (after the thesis evaluation)**

- Switch embeddings to Ollama's `all-minilm` (`EMBED_BACKEND=ollama`), reload the chunks, and rerun the evaluation. Then remove PyTorch from the host environment.
- Connect the bandit to real signals from the event log.
- Run the user study from the proposal (needs ethics approval and participants).

---

## What the thesis can and cannot claim

Can claim:
- Depth-capped retrieval changes which material reaches the model.
- Matched-depth answers are grounded in that material.

Cannot claim yet:
- Fine-tuning
- Learning gains
- Adaptive learning (bandit uses placeholder inputs)
- AR or SLAM results, unless measured in the evaluation
- Generalization beyond DNA