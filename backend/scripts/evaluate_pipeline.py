"""
Measure how well grouping and incident detection recover the incidents that were injected into the SYNTHETIC samples.

    python scripts/evaluate_pipeline.py                  # prints a report
    python scripts/evaluate_pipeline.py --json out.json  # also saves the numbers

How it works (all in a temporary folder, your real database is not touched):
  1. generate a sample and its answer key (which log line belongs to which injected scenario);
  2. load it through the real API and run the real analysis;
  3. for each scenario, find the detected incident that contains most of its error-level lines, then report
       recall     = share of the scenario's error-level lines that are inside that incident
       purity     = share of that incident's error-level lines that belong to the scenario
  4. count incidents that match no scenario (false alarms);
  5. repeat with different similarity thresholds, to show how sensitive the result is.

Important: these numbers come from invented data made by our own generator. They show the code does what it is meant
to do on that data. They are NOT a claim about accuracy on real production logs.
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

import logging  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402

from app.core.config import Settings  # noqa: E402
from app.main import create_app  # noqa: E402
from app.utils.sample_logs import generate  # noqa: E402

ERROR_LEVELS = {"ERROR", "CRITICAL"}


def read_all(client: TestClient, url: str, params: dict | None = None) -> list[dict]:
    """Read every page of a paged endpoint."""
    items: list[dict] = []
    page = 1
    while True:
        body = client.get(url, params={**(params or {}), "page": page, "page_size": 200}).json()
        items.extend(body["items"])
        if len(items) >= body["total"] or not body["items"]:
            return items
        page += 1


def evaluate(name: str, seed: int, similarity: float | None) -> dict:
    dataset = generate(name, seed)
    key = dataset.key
    with tempfile.TemporaryDirectory() as tmp:
        settings = Settings(_env_file=None, storage_dir=Path(tmp) / "storage", sample_runbook_dir=Path(tmp) / "rb",
                            max_upload_mb=50, max_log_records=100_000, ai_provider="none")
        with TestClient(create_app(settings)) as client:
            # Upload the generated file itself (the samples endpoint always uses seed 42, so it cannot match other keys).
            filename = key["file"]
            upload = client.post("/api/logs/upload", files={"file": (filename, dataset.files[filename].encode("utf-8"))})
            source = upload.json()["source"]
            body = {"source_id": source["id"]}
            if similarity is not None:
                body["similarity_threshold"] = similarity
            analysis = client.post("/api/logs/analyze", json=body).json()["analysis"]
            incidents = read_all(client, "/api/incidents", {"analysis_id": analysis["id"]})

            # Error-level line numbers for each incident, and for the whole file.
            incident_lines: dict[str, set[int]] = {}
            for inc in incidents:
                recs = read_all(client, f"/api/incidents/{inc['id']}/records", {"level": ["ERROR", "CRITICAL"]})
                incident_lines[inc["id"]] = {r["line_no"] for r in recs}
            level_by_line = {r["line_no"]: r["level"] for r in read_all(client, "/api/logs", {"source_id": source["id"]})}

    results = []
    matched_incidents: set[str] = set()
    for scenario, lines in key["lines_by_scenario"].items():
        if scenario in ("baseline", "noise"):
            continue
        truth = {ln for ln in lines if level_by_line.get(ln) in ERROR_LEVELS}
        if not truth:
            continue
        best_id, best_overlap = None, 0
        for inc_id, found in incident_lines.items():
            overlap = len(truth & found)
            if overlap > best_overlap:
                best_id, best_overlap = inc_id, overlap
        if best_id is None:
            results.append({"scenario": scenario, "found": False, "error_lines": len(truth), "recall": 0.0, "purity": 0.0})
            continue
        matched_incidents.add(best_id)
        found = incident_lines[best_id]
        label = next(i["label"] for i in incidents if i["id"] == best_id)
        results.append({"scenario": scenario, "found": True, "incident": label, "error_lines": len(truth),
                        "recall": round(best_overlap / len(truth), 3), "purity": round(best_overlap / len(found), 3)})

    noise_lines = {ln for s in ("noise",) for ln in key["lines_by_scenario"].get(s, []) if level_by_line.get(ln) in ERROR_LEVELS}
    return {
        "dataset": name, "seed": seed, "similarity_threshold": similarity, "records": len(level_by_line),
        "scenarios": results, "incidents_detected": len(incidents),
        "unmatched_incidents": len(incidents) - len(matched_incidents),
        "isolated_noise_error_lines": len(noise_lines),
        "noise_lines_inside_incidents": len(noise_lines & set().union(*incident_lines.values())) if incident_lines else 0,
    }


def print_report(result: dict) -> None:
    sim = result["similarity_threshold"]
    print(f"\n== {result['dataset']} (seed {result['seed']}, similarity threshold {sim if sim is not None else 'default'}) ==")
    print(f"{result['records']:,} records, {result['incidents_detected']} incidents detected, "
          f"{result['unmatched_incidents']} matching no injected scenario")
    print(f"{'scenario':<26}{'found':<8}{'incident':<10}{'error lines':>12}{'recall':>9}{'purity':>9}")
    for s in result["scenarios"]:
        print(f"{s['scenario']:<26}{'yes' if s['found'] else 'NO':<8}{s.get('incident', '-'):<10}{s['error_lines']:>12}{s['recall']:>9.2f}{s['purity']:>9.2f}")
    if result["isolated_noise_error_lines"]:
        print(f"isolated noise: {result['isolated_noise_error_lines']} error lines, "
              f"{result['noise_lines_inside_incidents']} of them inside an incident")


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate incident detection on the synthetic samples.")
    parser.add_argument("--seeds", type=int, nargs="+", default=[42, 7, 123], help="generator seeds to test")
    parser.add_argument("--thresholds", type=float, nargs="+", default=[0.3, 0.5, 0.7, 0.9], help="similarity thresholds for the sensitivity check")
    parser.add_argument("--json", type=Path, help="save all numbers to this file")
    args = parser.parse_args()
    logging.disable(logging.CRITICAL)  # keep the report readable

    runs = []
    print("SYNTHETIC DATA ONLY: these numbers do not describe accuracy on real logs.")
    print("\n### Default settings, several seeds")
    for name in ("application", "routing"):
        for seed in args.seeds:
            result = evaluate(name, seed, None)
            runs.append(result)
            print_report(result)

    print("\n### Sensitivity to the similarity threshold (seed 42)")
    sensitivity = []
    print(f"{'dataset':<13}{'threshold':>10}{'incidents':>11}{'unmatched':>11}{'min recall':>12}{'min purity':>12}")
    for name in ("application", "routing"):
        for threshold in args.thresholds:
            r = evaluate(name, 42, threshold)
            sensitivity.append(r)
            recalls = [s["recall"] for s in r["scenarios"]] or [0]
            purities = [s["purity"] for s in r["scenarios"]] or [0]
            print(f"{name:<13}{threshold:>10.2f}{r['incidents_detected']:>11}{r['unmatched_incidents']:>11}{min(recalls):>12.2f}{min(purities):>12.2f}")

    if args.json:
        args.json.write_text(json.dumps({"synthetic_data_only": True, "runs": runs, "sensitivity": sensitivity}, indent=2), encoding="utf-8")
        print(f"\nsaved {args.json}")


if __name__ == "__main__":
    main()
