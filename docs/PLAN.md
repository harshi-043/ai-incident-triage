# Implementation plan

This is the plan written at the start of the project. Decisions that changed while building are noted in
`docs/VERIFICATION.md` and the README.

## What gets built

An application that ingests application or routing logs, groups related errors, builds incident timelines,
retrieves relevant runbook sections (RAG), and suggests **read-only** diagnostic steps that link back to evidence.
It never runs a command, restarts a service or changes a configuration.

## Environment findings (checked before building)

| Item | Finding | Consequence |
|---|---|---|
| Python | 3.13.18 | Backend targets 3.12+ |
| Node | 22.23.4 | Frontend needs Node 22.12+ (Vite 7 / Vitest) |
| `faiss-cpu` | installs from PyPI | Used as the vector store, with a NumPy fallback |
| Hugging Face | blocked from the build workspace (HTTP 403) | A Sentence Transformers model cannot be downloaded here, so the default embedder is TF-IDF. The Sentence Transformers option is written but cannot be tested in this workspace |
| LLM API key | none | LLM provider code is tested with mocked HTTP only. No live provider call is claimed |

## Architecture

```text
Browser (React)  ->  FastAPI  ->  services  ->  ingestion / incident / rag / ai  ->  SQLite + FAISS index file
```

| Module | Folder | Job |
|---|---|---|
| Ingestion | `app/ingestion` | Detect format, parse CSV / TXT / JSONL, normalise levels and timestamps, validate, report counts |
| Incident | `app/incident` | Mask variable values into templates, group errors, detect incidents, build timelines and evidence links |
| RAG | `app/rag` | Load runbooks, chunk by heading, embed, index, retrieve, cite, refuse when relevance is low |
| AI | `app/ai` | Provider abstraction, evidence package, prompt, Pydantic-validated summary, deterministic fallback |
| Services | `app/services` | Orchestration used by the API (analysis, summaries, exports, dashboard) |
| Repositories | `app/repositories` | Database reads and writes |
| API | `app/api/routes` | REST endpoints |

## Key design decisions

1. **Facts, retrieved text and hypotheses are always labelled separately.** Every item returned to the UI has an
   `origin` of `observed`, `runbook`, `rule` or `ai_hypothesis`.
2. **Evidence is a list of log record ids.** Timeline events, groups and diagnostic steps all carry those ids,
   and `GET /api/logs/{id}` returns the record with its neighbours, so every claim can be checked.
3. **Grouping is two-step.** First exact grouping by (service, exception type, masked message template), then
   TF-IDF cosine similarity between templates with a configurable threshold. Similarity means "related wording", not
   "same root cause", and the UI says so.
4. **Incidents come from transparent rules** (time gap, minimum error count, severity, status codes, services).
   Each incident stores the rule values that created it.
5. **Retrieval works with no LLM.** TF-IDF + cosine is the default. If no chunk reaches the relevance threshold the
   answer is "no relevant source found", never a guess.
6. **The LLM is optional.** It receives a bounded evidence package, with logs wrapped as untrusted data. Its answer
   is validated against a Pydantic schema, and every evidence reference must exist, otherwise the answer is rejected
   and the deterministic summary is used.
7. **No execution path exists.** Nothing in the backend imports `subprocess` or calls `os.system`, `eval` or `exec`.
   A test checks this. Runbook commands are shown as text only.
8. **Synthetic data only.** A seeded generator makes logs with a separate answer key. The key is never an input to
   grouping, and is used only by the evaluation.

## Stages and checks

| Stage | Output | Check |
|---|---|---|
| 1 | Structure, environment findings, this plan | Folders exist, packages import |
| 2 | Config, models, parsers, upload API, sample generator | Ingestion tests |
| 3 | Normalisation, grouping, incidents, timelines | Grouping and incident tests, evaluation against answer key |
| 4 | Runbooks, chunking, index, retrieval | Retrieval tests, hit@k on sample questions |
| 5 | LLM layer, summaries, diagnostic steps | Mocked-provider tests, evidence-reference validation |
| 6-7 | Frontend pages wired to the API | Vitest, type check |
| 8 | Full test run, production build, browser run | Real outcomes recorded |
| 9 | README, architecture, verification record, zip | Another developer can follow it |
