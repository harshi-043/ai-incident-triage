# AI Log/Incident Triage Assistant

Load application or routing logs, group related errors, find incidents, look up matching runbooks, and get **read-only** diagnostic suggestions that link back to the exact log lines they came from.

> **Safety by design.** This application never runs commands, restarts services, changes configuration or applies fixes. It has no endpoint that does. Commands found in runbooks are shown as text for a person to read. Log text and runbook text are treated as untrusted data.
>
> **All sample data is synthetic** (invented logs and runbooks). Nothing here has been tested on real production logs.

## What it does
| Area | Details |
|---|---|
| Ingestion | CSV, TXT/LOG, JSON, JSON Lines. A quality report shows rejected lines, duplicates, missing timestamps and field coverage. |
| Error grouping | Messages are normalised (ids and numbers masked) and similar wording is grouped. |
| Incidents | Bursts of errors in time become incidents with severity, a plain-language reason ("why this was flagged"), a timeline, and related incidents. Status (open / investigating / resolved / ignored), reviewed flag and notes are saved in SQLite. |
| Runbook search (RAG) | TF-IDF by default; optional Sentence Transformers. FAISS index with a NumPy fallback. Results carry citations. Weak matches return **"no relevant source"** instead of a guess. |
| Investigation summary | Four separate sections: facts from the logs, runbook text, hypotheses (not confirmed), read-only checks. Every item has an origin badge (Observed / Runbook / Rule / AI hypothesis) and a support label (strong / moderate / weak, which is *not* a probability). |
| Optional AI | Off by default. When enabled per request, a bounded, clipped and redacted evidence package is sent to the provider you configured. Output must be valid JSON and cite real record ids, otherwise the app falls back to the non-AI summary. |
| Exports | Markdown, JSON, CSV for one incident or the whole report. CSV cells that could run as spreadsheet formulas are neutralised. |

The app is fully usable **without any paid AI key**.

## Requirements
* Python 3.12 or newer (built and tested on 3.13)
* Node.js 22.12 or newer

## Run it (macOS / Linux)
```bash
# 1. backend
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --port 8000

# 2. frontend (a second terminal)
cd frontend
npm install
npm run dev
```
Open http://localhost:5173. Click **Load sample** on the dashboard, then **Find incidents**.

## Run it (Windows PowerShell)
```powershell
cd backend
py -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --port 8000
```
Second PowerShell window:
```powershell
cd frontend
npm install
npm run dev
```
If activation is blocked, run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once. *(Windows was not tested by the author. Treat these steps as unverified.)*

API documentation (Swagger) is at http://127.0.0.1:8000/docs.

## Try the runbook search
Go to **Knowledge Base**, click **Load sample runbooks**, and search for `HikariPool getConnection timed out`. Then search `No space left on device`: no runbook covers it, so you get "no relevant source". That is the intended behaviour.

## Turning on AI (optional)
1. Copy `backend/.env.example` to `backend/.env`.
2. Set `AI_PROVIDER` (`anthropic`, `openai` or `openai_compatible`), `AI_MODEL` and `AI_API_KEY`. For `openai_compatible` also set `AI_BASE_URL`.
3. Restart the backend. **Settings** shows whether a key is set (never the key itself), and the AI Investigation page then offers an "Also ask an AI provider" checkbox.

Privacy: with AI on, up to `AI_MAX_EVIDENCE_RECORDS` log records of the chosen incident (clipped, with emails, IP addresses and tokens hidden) plus runbook excerpts leave your machine for that provider. Keys come only from environment variables and are never stored or logged. Do not commit `.env`.

## Settings you can change (environment variables)
`MAX_UPLOAD_MB`, `MAX_LOG_RECORDS`, `MAX_RUNBOOK_MB`, `SIMILARITY_THRESHOLD`, `INCIDENT_GAP_MINUTES`, `INCIDENT_MIN_ERRORS`, `MIN_RELEVANCE`, `EMBEDDING_BACKEND` (`tfidf` or `sentence_transformers`, the latter needs `pip install sentence-transformers`), `CORS_ORIGINS`, `STORAGE_DIR`. Defaults are in `backend/app/core/config.py`.

## Tests
```bash
cd backend && python -m pytest -q          # 236 tests
cd frontend && npm test                    # 29 tests
cd frontend && npm run build               # type check + production build
python scripts/evaluate_pipeline.py        # (in backend/) detection vs injected synthetic incidents
python scripts/evaluate_retrieval.py       # (in backend/) retrieval hit rate and threshold sweep
python scripts/generate_sample_logs.py     # (in backend/) write synthetic logs to data/sample_logs
```
See [docs/VERIFICATION.md](docs/VERIFICATION.md) for what was run and what was **not**.

## Architecture
```
Browser (React) -> FastAPI routes -> services -> ingestion | incidents | rag | ai -> SQLite + vector file
```
* `backend/app/ingestion` parsing and quality report. `app/incident` grouping, detection, timeline. `app/rag` loader, chunker, vector index, retriever. `app/ai` evidence, prompts, providers, safety, summary. `app/api/routes` HTTP layer. `app/services` orchestration and exports.
* `frontend/src` pages, components, `api/` (one function per endpoint), `context/` (selected log source).

### Main API endpoints (all under `/api`)
`GET /health`, `GET /settings`, `POST /logs/upload`, `GET|POST /logs/samples`, `GET /logs`, `POST /logs/analyze`, `GET /dashboard/summary`, `GET /incidents`, `GET|PATCH /incidents/{id}`, `POST|DELETE /incidents/{id}/notes`, `GET /incidents/{id}/runbooks`, `POST /incidents/{id}/summarize`, `POST /incidents/{id}/ask`, `GET /incidents/{id}/export`, `GET /reports/export`, `GET|POST /knowledge/...`. Errors always look like `{"error": {"code", "message", "details"}}`. Full list: `/docs`.

## Safety measures
* No code path runs shell commands or evaluates text. A test scans the source for forbidden calls (`subprocess`, `os.system`, `eval`, `exec`, `pickle`, ...).
* Uploads: extension allow-list, size limit, safe file names, no path traversal.
* Log text sent to an AI is clipped, redacted and wrapped in per-request random markers, and the model is told it is data.
* Recommendations that read like changes to a system (restart, delete, set, apply...) are moved to "Mentioned but not suggested".

## Known limits (please read)
* Detection and retrieval were tuned and measured only on **synthetic** data made by the same author. Real logs will behave differently.
* The "no relevant source" threshold is tuned on a small set and is fragile. TF-IDF can miss very short keyword queries.
* The Sentence Transformers path and the live AI providers were **not** tested against real services (the build environment could not reach them). Provider code is tested with mocked HTTP only.
* Without AI, the Ask box only finds matching log records and runbook sections. It cannot answer reasoning questions such as "which service failed first?".
* Local single-user tool: no login, no multi-user access control. Not deployed anywhere.
* Not tested on Windows or macOS.

## Troubleshooting
| Problem | Fix |
|---|---|
| "Cannot reach the API" | Start the backend on port 8000 first. |
| `pip install` fails on `faiss-cpu` | Remove that line; the app falls back to NumPy search. |
| Port 8000 or 5173 busy | Start uvicorn with `--port 8001` and set `VITE_API_BASE_URL` / change the proxy in `frontend/vite.config.ts`. |
| Upload rejected | Check the extension (csv, txt, log, json, jsonl, ndjson) and the size limit. |
| Want a clean start | Stop the backend and delete `backend/storage`. |

## Publishing to GitHub
```bash
git init && git add . && git commit -m "AI Log/Incident Triage Assistant"
```
`.gitignore` already excludes `.venv`, `node_modules`, `storage`, `.env` and generated logs. Check `git status` shows no `.env` before pushing. A frontend-only demo is not useful here because the backend does the analysis.
