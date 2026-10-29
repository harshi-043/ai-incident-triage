# Verification report

Everything below was run in the build environment (Linux, Python 3.13, Node 22) on 2026-10-28. Nothing was run on Windows or macOS, and nothing is deployed.

## Automated tests
| Suite | Command | Result |
|---|---|---|
| Backend | `cd backend && python -m pytest -q` | 236 passed, 1 warning (a deprecation notice from the test client library) |
| Frontend | `cd frontend && npm test` | 29 passed in 4 files |
| Type check + production build | `cd frontend && npm run build` | passes |

## Live browser run (Chromium, real UI, real backend, fresh empty storage)
26 of 26 checks passed: empty state; load synthetic sample; run analysis; incident list and detail; status change and note surviving a page reload; evidence drawer; summary without AI (facts / runbook text / hypotheses / read-only checks); Ask box; runbook upload of samples; search hit and "no relevant source"; Markdown report download; settings shows the key as "not set"; unknown route; no horizontal scroll at 390 px wide on three pages; no browser console errors.

## Measured quality (synthetic data only)
Run `python scripts/evaluate_pipeline.py` and `python scripts/evaluate_retrieval.py` in `backend/` to reproduce. Numbers are printed by the scripts; they are not copied here so they cannot go stale.
* Incident detection is scored against incidents our own generator injected. It says nothing about real production logs.
* Retrieval questions were written by the same author as the runbooks, so they are friendlier than real questions. The "no relevant source" threshold (0.16) was picked from that small set and is fragile.

## NOT verified
* The Sentence Transformers search path (the model could not be downloaded here). Only the TF-IDF path and the fallback message are tested.
* The Anthropic / OpenAI / compatible provider code was tested with mocked HTTP only. Request formats were not confirmed against live services.
* Windows and macOS installs. Real-world log accuracy. Large files near the limits beyond the unit tests. Deployment.
* Screen readers. Keyboard use was designed in (focus, Escape, Enter on rows) but only partly tested.
