"""
Measure runbook retrieval and choose the "no relevant source" threshold from data instead of guessing.

    python scripts/evaluate_retrieval.py

It loads the bundled sample runbooks into a temporary database and asks two kinds of questions:
  * in-scope questions, each with the runbook that SHOULD answer it  -> hit@1 and hit@3
  * out-of-scope questions that no runbook covers (the correct answer is "no relevant source")
Then it sweeps the relevance threshold and shows what each value would keep and reject.

Limits you should know about: the questions were written by the same person who wrote the runbooks (me), so they
are friendlier than real questions would be, and the set is small (see the counts printed below). The numbers show
the retrieval code works on this material. They are not a promise about other runbooks.
"""
from __future__ import annotations

import logging
import sys
import tempfile
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from fastapi.testclient import TestClient  # noqa: E402

from app.core.config import Settings  # noqa: E402
from app.main import create_app  # noqa: E402

IN_SCOPE = [
    # (question, expected runbook file)
    ("connection pool exhausted, requests are waiting for a database connection", "database-connectivity.md"),
    ("HikariPool getConnection timed out", "database-connectivity.md"),
    ("the database refuses new connections, we hit the connection limit", "database-connectivity.md"),
    ("how do I find long running queries or lock waits during the incident", "database-connectivity.md"),
    ("services return 503 because they cannot get a database connection", "database-connectivity.md"),
    ("API responses are very slow after the cache was restarted", "api-latency.md"),
    ("cache hit ratio dropped and request durations went up", "api-latency.md"),
    ("requests take several seconds, how do I find where the time is spent", "api-latency.md"),
    ("latency spike on the orders endpoint compared with the baseline", "api-latency.md"),
    ("payments returns HTTP 500 after the latest release", "http-5xx-errors.md"),
    ("the same NullPointerException appears in every request", "http-5xx-errors.md"),
    ("502 bad gateway from the gateway after a deployment, should we roll back", "http-5xx-errors.md"),
    ("error rate per endpoint jumped right after a deploy", "http-5xx-errors.md"),
    ("BGP session down and packet loss on the link", "network-timeouts.md"),
    ("traffic failed over to the backup route and latency is higher", "network-timeouts.md"),
    ("interface is flapping and has error counters", "network-timeouts.md"),
    ("connection timed out, no route to host between two sites", "network-timeouts.md"),
    ("many failed logins from a single IP address", "authentication-failures.md"),
    ("invalid credentials errors spiked for many accounts", "authentication-failures.md"),
    ("users are locked out after repeated failed attempts", "authentication-failures.md"),
    ("JWT signature verification failed after the signing key was rotated", "authentication-failures.md"),
    ("401 unauthorized for every user at the same time", "authentication-failures.md"),
]

OUT_OF_SCOPE = [
    "java.io.IOException: No space left on device writing journal.log",
    "the disk is full on the inventory server and writes fail",
    "the kernel out of memory killer terminated the process",
    "kernel panic after the operating system upgrade",
    "kafka consumer lag keeps growing on the orders topic",
    "how do I bake sourdough bread",
    "what is the weather forecast for tomorrow",
    "the office printer is offline",
    "CPU thermal throttling on the build server",
    "garbage collection pauses in the JVM heap",
]


def main() -> None:
    logging.disable(logging.CRITICAL)
    with tempfile.TemporaryDirectory() as tmp:
        settings = Settings(_env_file=None, storage_dir=Path(tmp) / "s", min_relevance=0.0)  # 0.0: see every score
        with TestClient(create_app(settings)) as client:
            client.post("/api/knowledge/samples")
            status = client.get("/api/knowledge/status").json()

            def ask(q: str) -> list[tuple[str, float]]:
                hits = client.post("/api/knowledge/search", json={"query": q, "top_k": 10}).json()["results"]
                docs: list[tuple[str, float]] = []  # one entry per document, best chunk first
                for h in hits:
                    if h["filename"] not in [d for d, _ in docs]:
                        docs.append((h["filename"], h["score"]))
                return docs

            in_rows = [(q, exp, ask(q)) for q, exp in IN_SCOPE]
            out_rows = [(q, ask(q)) for q in OUT_OF_SCOPE]

    print("SYNTHETIC runbooks and hand-written questions. Retrieval backend:", status["retrieval"]["backend"],
          "| vector store:", status["retrieval"]["vector_store"], f"| {status['documents']} documents, {status['chunks']} chunks")
    hit1 = sum(1 for _, exp, docs in in_rows if docs and docs[0][0] == exp)
    hit3 = sum(1 for _, exp, docs in in_rows if exp in [d for d, _ in docs[:3]])
    n = len(in_rows)
    print(f"\nIn-scope questions: {n}   hit@1 = {hit1}/{n}   hit@3 = {hit3}/{n}")
    for q, exp, docs in in_rows:
        if not docs or docs[0][0] != exp:
            print(f"  MISS  {q!r}\n        expected {exp}, got {docs[:2]}")

    in_scores = sorted(docs[0][1] for _, exp, docs in in_rows if docs and docs[0][0] == exp)
    out_scores = sorted(docs[0][1] if docs else 0.0 for _, docs in out_rows)
    print(f"\nTop score when the answer is right : min {in_scores[0]:.3f}  median {in_scores[len(in_scores)//2]:.3f}  max {in_scores[-1]:.3f}")
    print(f"Top score for out-of-scope questions: min {out_scores[0]:.3f}  median {out_scores[len(out_scores)//2]:.3f}  max {out_scores[-1]:.3f}")

    print("\nThreshold sweep (a question is 'answered' when its best chunk scores at least the threshold)")
    print(f"{'threshold':>9}{'right answers kept':>20}{'out-of-scope rejected':>24}")
    for t in [0.05, 0.08, 0.10, 0.12, 0.14, 0.16, 0.18, 0.20, 0.22, 0.25, 0.30]:
        kept = sum(1 for _, exp, docs in in_rows if docs and docs[0][0] == exp and docs[0][1] >= t)
        rejected = sum(1 for _, docs in out_rows if not docs or docs[0][1] < t)
        print(f"{t:>9.2f}{kept:>14}/{n:<5}{rejected:>18}/{len(out_rows)}")


if __name__ == "__main__":
    main()
