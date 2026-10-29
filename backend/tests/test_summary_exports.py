"""Summaries (without AI), diagnostic steps, questions, exports and the settings view."""
from __future__ import annotations

import csv
import io
import json

import pytest

from app.ai.safety import looks_like_change
from tests.helpers import big_settings, error_code


@pytest.fixture
def settings(tmp_path):
    return big_settings(tmp_path)


@pytest.fixture
def world(client):
    client.post("/api/knowledge/samples")
    src = client.post("/api/logs/samples", json={"name": "application"}).json()["source"]
    client.post("/api/logs/analyze", json={"source_id": src["id"]})
    items = client.get("/api/incidents", params={"source_id": src["id"], "sort": "number"}).json()["items"]
    return src, items  # items[0] = database pool incident, items[4] = disk full (no runbook)


def summarize(client, incident, **body):
    resp = client.post(f"/api/incidents/{incident['id']}/summarize", json=body)
    assert resp.status_code == 200
    return resp.json()["summary"]


def all_record_ids(client, incident):
    ids, page = set(), 1
    while True:
        body = client.get(f"/api/incidents/{incident['id']}/records", params={"page_size": 200, "page": page}).json()
        ids |= {r["id"] for r in body["items"]}
        if len(ids) >= body["total"] or not body["items"]:
            return ids
        page += 1


def test_summary_separates_facts_runbook_text_and_hypotheses(client, world):
    _, items = world
    s = summarize(client, items[0])
    assert s["generated_by"] == "deterministic" and s["used_ai"] is False and s["ai_available"] is False and s["ai_narrative"] is None
    assert s["facts"] and {f["origin"] for f in s["facts"]} == {"observed"}
    assert s["retrieved"] and {r["origin"] for r in s["retrieved"]} == {"runbook"}
    assert s["hypotheses"] and {h["origin"] for h in s["hypotheses"]} <= {"rule", "ai_hypothesis"}
    assert all("not a confirmed cause" in h["caveat"] for h in s["hypotheses"])
    assert {st["origin"] for st in s["steps"]} <= {"runbook", "rule", "ai_hypothesis"}
    assert "never runs commands" in s["notice"]
    assert any("root cause" in note for note in s["limitations"])


def test_every_cited_record_exists_in_the_incident(client, world):
    _, items = world
    for incident in items:
        s = summarize(client, incident)
        valid = all_record_ids(client, incident)
        cited = [i for f in s["facts"] for i in f["evidence_ids"]] + [i for h in s["hypotheses"] for i in h["evidence_ids"]] \
            + [i for st in s["steps"] for i in st["evidence_ids"]]
        assert cited and set(cited) <= valid, f"{incident['label']}: evidence outside the incident"
        for step in s["steps"]:
            assert step["evidence_ids"], "a step without evidence"


def test_steps_are_read_only_labelled_and_numbered(client, world):
    _, items = world
    for incident in items:
        s = summarize(client, incident)
        assert [st["id"] for st in s["steps"]] == [f"step-{i}" for i in range(1, len(s["steps"]) + 1)]
        assert len({st["title"].lower() for st in s["steps"]}) == len(s["steps"]), "duplicate steps"
        for st in s["steps"]:
            assert st["read_only"] is True and st["strength"] in {"strong", "moderate", "weak"} and st["strength_reason"]
            assert st["expected_observation"] and st["evidence_match"] in {"specific", "general"}
            assert looks_like_change(f"{st['title']}. {st['instruction']}") is None, st["title"]
            assert (st["origin"] == "runbook") == bool(st["citation"]) or st["origin"] == "rule"
            if st["origin"] == "runbook":
                assert st["citation"].endswith(("Diagnostic steps (read-only)",))
        assert s["not_suggested"] == []  # the bundled runbooks contain only read-only steps


def test_documented_commands_appear_as_text_in_a_step(client, world):
    _, items = world
    s = summarize(client, items[0])
    with_commands = [st for st in s["steps"] if st["documented_commands"]]
    assert with_commands and any("pg_stat_activity" in c for st in with_commands for c in st["documented_commands"])
    assert all("does not run" in st["instruction"] for st in with_commands)


def test_incident_without_a_runbook_says_so_and_still_has_rule_steps(client, world):
    _, items = world
    disk = summarize(client, items[4])
    assert disk["no_relevant_source"] is True and disk["retrieved"] == []
    assert any("No relevant runbook" in n for n in disk["limitations"])
    assert disk["steps"] and {st["origin"] for st in disk["steps"]} == {"rule"}
    assert all(st["citation"] is None and st["strength"] == "moderate" for st in disk["steps"])


def test_matching_runbook_gives_cited_steps_for_each_other_incident(client, world):
    _, items = world
    expected = {0: "database-connectivity.md", 1: "api-latency.md", 2: "authentication-failures.md", 3: "http-5xx-errors.md"}
    for index, filename in expected.items():
        s = summarize(client, items[index])
        assert s["retrieved"][0]["citation"].startswith(filename), items[index]["label"]
        assert any(st["origin"] == "runbook" and st["citation"].startswith(filename) for st in s["steps"])


def test_summary_is_saved_and_listed_as_latest(client, world):
    _, items = world
    assert client.get(f"/api/incidents/{items[0]['id']}/summary").json()["summary"] is None
    first = summarize(client, items[0])
    saved = client.get(f"/api/incidents/{items[0]['id']}/summary").json()["summary"]
    assert saved["headline"] == first["headline"] and saved["steps"] == first["steps"]
    detail = client.get("/api/dashboard/summary").json()
    assert any("Summary generated" in a["detail"] for a in detail["recent_activity"])


def test_asking_for_ai_without_a_provider_is_a_clear_non_error(client, world):
    _, items = world
    s = summarize(client, items[0], use_ai=True)
    assert s["used_ai"] is False and "AI_PROVIDER=none" in s["ai_error"] and s["facts"]


def test_ask_returns_matching_records_and_runbook_sections(client, world):
    _, items = world
    body = client.post(f"/api/incidents/{items[0]['id']}/ask", json={"question": "connection pool timeout"}).json()
    assert body["answer_origin"] == "retrieval" and body["used_ai"] is False
    assert body["evidence"] and body["runbook_sources"]
    assert any("pool" in e["message"].lower() for e in body["evidence"])
    valid = all_record_ids(client, items[0])
    assert {e["id"] for e in body["evidence"]} <= valid


def test_ask_with_no_match(client, world):
    _, items = world
    body = client.post(f"/api/incidents/{items[0]['id']}/ask", json={"question": "sourdough bread recipe"}).json()
    assert body["evidence"] == [] and body["runbook_sources"] == [] and "No log record" in body["answer"]
    assert client.post(f"/api/incidents/{items[0]['id']}/ask", json={"question": "x"}).status_code == 422
    assert client.post(f"/api/incidents/{items[0]['id']}/ask", json={"question": "q" * 501}).status_code == 422


def test_summary_endpoints_reject_unknown_incidents(client):
    fake = "inc_" + "0" * 16
    assert client.post(f"/api/incidents/{fake}/summarize", json={}).status_code == 404
    assert client.get(f"/api/incidents/{fake}/summary").status_code == 404
    assert client.post(f"/api/incidents/{fake}/ask", json={"question": "what happened"}).status_code == 404
    assert client.get(f"/api/incidents/{fake}/export").status_code == 404


# ---------------------------------------------------------------- exports
def test_markdown_export_has_all_sections_and_labels(client, world):
    _, items = world
    client.post(f"/api/incidents/{items[0]['id']}/notes", json={"body": "Checked the pool settings."})
    resp = client.get(f"/api/incidents/{items[0]['id']}/export", params={"format": "md"})
    assert resp.status_code == 200 and resp.headers["content-type"].startswith("text/markdown")
    assert resp.headers["content-disposition"].startswith('attachment; filename="INC-1-') and resp.headers["x-content-type-options"] == "nosniff"
    text = resp.text
    for heading in ("## Why this was flagged", "## Facts (observed", "## Timeline", "## Runbook sections found", "## Hypotheses (not confirmed)",
                    "## Suggested read-only checks", "## Analyst notes", "## Evidence records", "## Limitations"):
        assert heading in text
    assert "Checked the pool settings." in text and "synthetic sample data" in text and "never runs commands" in text
    assert "[rule," in text and "[runbook," in text


def test_json_export_is_valid_and_matches_the_screen(client, world):
    _, items = world
    data = json.loads(client.get(f"/api/incidents/{items[0]['id']}/export", params={"format": "json"}).text)
    assert data["incident"]["label"] == "INC-1" and data["summary"]["facts"] and data["records"] and data["timeline"]
    assert data["source"]["kind"] == "sample"


def test_csv_export_neutralises_spreadsheet_formulas(client):
    log = "".join(f"2026-03-10 09:00:{i:02d},000 ERROR [svc] =HYPERLINK(\"http://evil\",\"x\") failed request_id=r{i}\n" for i in range(6))
    src = client.post("/api/logs/upload", files={"file": ("a.log", log.encode())}).json()["source"]
    client.post("/api/logs/analyze", json={"source_id": src["id"], "min_errors": 2})
    inc = client.get("/api/incidents", params={"source_id": src["id"]}).json()["items"][0]
    text = client.get(f"/api/incidents/{inc['id']}/export", params={"format": "csv"}).text
    rows = list(csv.DictReader(io.StringIO(text)))
    assert rows and all(not r["message"].startswith("=") for r in rows) and any(r["message"].startswith("'=HYPERLINK") for r in rows)


def test_markdown_export_escapes_table_breaking_text(client):
    log = "".join(f"2026-03-10 09:00:{i:02d},000 ERROR [svc] bad | pipe `tick` value request_id=r{i}\n" for i in range(6))
    src = client.post("/api/logs/upload", files={"file": ("a.log", log.encode())}).json()["source"]
    client.post("/api/logs/analyze", json={"source_id": src["id"], "min_errors": 2})
    inc = client.get("/api/incidents", params={"source_id": src["id"]}).json()["items"][0]
    text = client.get(f"/api/incidents/{inc['id']}/export", params={"format": "md"}).text
    row = next(line for line in text.splitlines() if line.startswith("| ") and "bad" in line)
    assert "bad \\| pipe 'tick' value" in row


def test_export_format_validation(client, world):
    _, items = world
    assert client.get(f"/api/incidents/{items[0]['id']}/export", params={"format": "exe"}).status_code == 422


def test_report_export(client, world):
    src, _ = world
    md = client.get("/api/reports/export", params={"source_id": src["id"], "format": "md"})
    assert md.status_code == 200 and "# Incident report" in md.text and "INC-5" in md.text and "synthetic sample data" in md.text
    rows = list(csv.DictReader(io.StringIO(client.get("/api/reports/export", params={"format": "csv"}).text)))
    rank = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    severities = [rank[r["severity"]] for r in rows]
    assert severities == sorted(severities), "the report should list the most severe incidents first"
    assert len(rows) == 5
    data = json.loads(client.get("/api/reports/export", params={"format": "json"}).text)
    assert len(data["incidents"]) == 5 and data["analysis"]["stats"]["incident_count"] == 5


def test_report_export_errors(client):
    assert client.get("/api/reports/export").status_code == 404  # nothing loaded
    src = client.post("/api/logs/samples", json={"name": "routing"}).json()["source"]
    resp = client.get("/api/reports/export", params={"source_id": src["id"]})
    assert resp.status_code == 409 and error_code(resp) == "analysis_needed"
    assert client.get("/api/reports/export", params={"source_id": "src_" + "0" * 16}).status_code == 404


# ---------------------------------------------------------------- settings
def test_settings_view_never_contains_the_key(tmp_path):
    from fastapi.testclient import TestClient

    from app.main import create_app

    secret = "sk-live-do-not-leak-0123456789"
    with TestClient(create_app(big_settings(tmp_path, ai_provider="anthropic", ai_api_key=secret, ai_model="m"))) as c:
        resp = c.get("/api/settings")
        assert resp.status_code == 200 and secret not in resp.text
        ai = resp.json()["ai"]
        assert ai["key_set"] is True and ai["ready"] is True and ai["provider"] == "anthropic"
        for url in ("/api/health", "/api/knowledge/status", "/openapi.json"):
            assert secret not in c.get(url).text


def test_settings_view_reports_problems(client):
    body = client.get("/api/settings").json()
    assert body["ai"]["provider"] == "none" and body["ai"]["ready"] is False and body["ai"]["key_set"] is False
    assert "never runs commands" in body["safety"] and "retrieval" in body and "detection_defaults" in body
