"""Exports: Markdown, JSON and CSV for one incident or for a whole analysis. Exports contain the same labels as the screen."""
from __future__ import annotations

import csv
import io
import json
import re
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.ai.safety import clip
from app.core.config import Settings
from app.ingestion.normalize import iso_z
from app.models.tables import Analysis, Incident, LogSource
from app.rag.retriever import KnowledgeIndex
from app.repositories import incidents as repo
from app.services import summary_service

FORMULA_STARTS = ("=", "+", "-", "@", "\t", "\r")
MAX_EXPORT_RECORDS = 1000


def csv_safe(value: Any) -> Any:
    """Spreadsheet programs run text that starts with = + - @ as a formula. A leading apostrophe turns it back into text."""
    if isinstance(value, str) and value.startswith(FORMULA_STARTS):
        return "'" + value
    return value


def to_csv(header: list[str], rows: list[list[Any]]) -> str:
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(header)
    for row in rows:
        writer.writerow([csv_safe(v) for v in row])
    return out.getvalue()


def safe_filename(label: str, title: str, extension: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "-", title).strip("-").lower()[:40]
    return f"{label}-{slug}.{extension}" if slug else f"{label}.{extension}"


def _cell(text: Any) -> str:
    return clip(str(text), 220).replace("|", "\\|").replace("`", "'")


def _summary_dict(session: Session, settings: Settings, kb: KnowledgeIndex, incident: Incident) -> dict[str, Any]:
    saved = summary_service.latest_summary(session, incident.id)
    if saved is not None:
        return saved
    return summary_service.build_summary(session, settings, kb, incident, use_ai=False, provider=None).model_dump()


def incident_export_data(session: Session, settings: Settings, kb: KnowledgeIndex, incident: Incident) -> dict[str, Any]:
    ctx = summary_service._context(session, incident)
    analysis = repo.get_analysis(session, incident.analysis_id)
    source = session.get(LogSource, analysis.source_id) if analysis else None
    return {
        "exported_at": iso_z(datetime.now(timezone.utc).replace(tzinfo=None)),
        "source": {"name": source.name, "kind": source.kind} if source else None,
        "incident": {**repo.incident_to_dict(incident), "explanation": incident.explanation},
        "timeline": incident.timeline,
        "summary": _summary_dict(session, settings, kb, incident),
        "notes": [repo.note_to_dict(n) for n in sorted(incident.notes, key=lambda n: n.created_at)],
        "records": ctx["records"][:MAX_EXPORT_RECORDS],
        "notice": "Suggestions only. This application never runs commands or changes any system.",
    }


def incident_markdown(data: dict[str, Any]) -> str:
    inc, summary = data["incident"], data["summary"]
    lines = [f"# {inc['label']}: {inc['title']}", "",
             f"- Severity: **{inc['severity']}**   Status: **{inc['status']}**   Reviewed: {'yes' if inc['reviewed'] else 'no'}",
             f"- Window: {inc['first_seen']} to {inc['last_seen']}   Services: {', '.join(inc['services'])}",
             f"- Error-level records: {inc['error_count']} (all records in the incident: {inc['record_count']})",
             f"- Exported: {data['exported_at']}"]
    if data["source"]:
        note = " (synthetic sample data)" if data["source"]["kind"] == "sample" else ""
        lines.append(f"- Log source: {data['source']['name']}{note}")
    lines += ["", f"> {data['notice']}", "", "## Why this was flagged as an incident", "", inc["explanation"], "",
              "## Facts (observed in the logs)", ""]
    lines += [f"- {f['statement']} _(records: {', '.join(map(str, f['evidence_ids']))})_" for f in summary["facts"]] or ["- None."]
    lines += ["", "## Timeline", ""]
    lines += [f"- {e['time']} **{e['title']}** [{e['origin']}] _(records: {', '.join(map(str, e['evidence_ids']))})_" for e in data["timeline"]]
    lines += ["", "## Runbook sections found (retrieved text, not instructions to run)", ""]
    if summary["retrieved"]:
        for r in summary["retrieved"]:
            lines += [f"- **{r['citation']}** ({r['relevance']} match): {clip(r['text'], 300)}"]
    else:
        lines.append("- No relevant source was found in the knowledge base.")
    lines += ["", "## Hypotheses (not confirmed)", ""]
    lines += [f"- [{h['origin']}, {h['strength']}] {h['statement']} {h['reasoning']} _(records: {', '.join(map(str, h['evidence_ids']))})_"
              for h in summary["hypotheses"]] or ["- None."]
    if summary.get("ai_narrative"):
        lines += ["", "## AI narrative (written by a language model, may be wrong)", "", summary["ai_narrative"]]
    lines += ["", "## Suggested read-only checks", ""]
    for s in summary["steps"]:
        cite = f", source: {s['citation']}" if s["citation"] else ""
        lines += [f"{s['id'].split('-')[1]}. **{s['title']}** [{s['origin']}, {s['strength']}{cite}]",
                  f"   - {s['instruction']}", f"   - Expect: {s['expected_observation']}",
                  f"   - Evidence records: {', '.join(map(str, s['evidence_ids']))} ({s['evidence_match']} match)"]
        for c in s["documented_commands"]:
            lines.append(f"   - Documented command (text only, not run by this tool): `{c.replace('`', chr(39))}`")
    if summary["not_suggested"]:
        lines += ["", "## Mentioned but not suggested (reads like a change)", ""]
        lines += [f"- {n['text']} - {n['reason']}" for n in summary["not_suggested"]]
    lines += ["", "## Analyst notes", ""]
    lines += [f"- {n['created_at']}: {n['body']}" for n in data["notes"]] or ["- None."]
    lines += ["", "## Evidence records", "", "| id | time | level | service | message |", "|---|---|---|---|---|"]
    lines += [f"| {r['id']} | {r['timestamp']} | {r['level']} | {_cell(r['service'])} | {_cell(r['message'])} |" for r in data["records"][:50]]
    lines += ["", "## Limitations", ""] + [f"- {n}" for n in summary["limitations"]]
    return "\n".join(lines) + "\n"


def incident_records_csv(data: dict[str, Any]) -> str:
    cols = ["id", "line_no", "timestamp", "level", "service", "host", "request_id", "endpoint", "http_status", "latency_ms", "exception_type", "message"]
    return to_csv(cols, [[r.get(c) for c in cols] for r in data["records"]])


# ---- whole-analysis report ------------------------------------------------------------------------------------------
def report_data(session: Session, analysis: Analysis, source: LogSource) -> dict[str, Any]:
    rows, _ = repo.query_incidents(session, analysis_id=analysis.id, source_id=None, severities=None, statuses=None, reviewed=None, q=None,
                                   service=None, sort="severity", order="asc", page=1, page_size=200)
    return {"exported_at": iso_z(datetime.now(timezone.utc).replace(tzinfo=None)),
            "source": {"name": source.name, "kind": source.kind, "records": source.record_count},
            "analysis": {"id": analysis.id, "params": analysis.params, "stats": analysis.stats},
            "incidents": [repo.incident_to_dict(i) for i in rows],
            "notice": "Suggestions only. This application never runs commands or changes any system."}


def report_markdown(data: dict[str, Any]) -> str:
    src = data["source"]
    lines = ["# Incident report", "", f"- Log source: {src['name']} ({src['records']:,} records)" + (" - synthetic sample data" if src["kind"] == "sample" else ""),
             f"- Exported: {data['exported_at']}", f"- Incidents: {len(data['incidents'])}",
             f"- Detection settings: {json.dumps(data['analysis']['params'])}", "", f"> {data['notice']}", "",
             "| incident | severity | status | window | services | error records | title |", "|---|---|---|---|---|---|---|"]
    for i in data["incidents"]:
        lines.append(f"| {i['label']} | {i['severity']} | {i['status']} | {i['first_seen']} to {i['last_seen']} | {_cell(', '.join(i['services']))} | "
                     f"{i['error_count']} | {_cell(i['title'])} |")
    lines += ["", "Incidents are grouped from timing and message wording. This does not establish a root cause."]
    return "\n".join(lines) + "\n"


def report_csv(data: dict[str, Any]) -> str:
    cols = ["label", "severity", "status", "reviewed", "first_seen", "last_seen", "error_count", "record_count", "services", "title"]
    return to_csv(cols, [[i["label"], i["severity"], i["status"], i["reviewed"], i["first_seen"], i["last_seen"], i["error_count"],
                          i["record_count"], "; ".join(i["services"]), i["title"]] for i in data["incidents"]])
