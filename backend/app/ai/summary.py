"""The deterministic part of an incident summary: facts, hypotheses from fixed rules, and limitations. No AI involved."""
from __future__ import annotations

from typing import Any

from app.ai.safety import clip
from app.ai.schemas import Fact, Hypothesis, RetrievedPoint

FACT_EVENT_KINDS = ("early_warning", "http_5xx", "latency_threshold", "context_event", "peak")


def build_headline(incident: dict[str, Any]) -> str:
    services = incident["services"]
    where = services[0] if len(services) == 1 else f"{len(services)} services"
    top = incident["top_patterns"][0]["title"] if incident["top_patterns"] else ""
    return clip(f"{incident['label']} ({incident['severity']}): {incident['error_count']} error-level records in {where}"
                f"{' - ' + top if top else ''}", 220)


def build_facts(incident: dict[str, Any], timeline: list[dict[str, Any]], group_samples: dict[str, list[int]]) -> list[Fact]:
    facts: list[Fact] = []
    first_error = next((e for e in timeline if e["kind"] == "first_error"), None)
    last_error = next((e for e in timeline if e["kind"] == "last_error"), None)
    anchor = (first_error["evidence_ids"] if first_error else []) + (last_error["evidence_ids"] if last_error else [])
    if anchor:
        facts.append(Fact(
            statement=f"{incident['error_count']} error-level records were logged between {incident['first_seen']} and {incident['last_seen']} "
                      f"in {', '.join(incident['services'])}.", evidence_ids=anchor))
    for pattern in incident["top_patterns"][:3]:
        ids = group_samples.get(pattern.get("group_id", ""), [])[:3]
        if ids:
            facts.append(Fact(statement=f"{pattern['count']} records match the pattern: {clip(pattern['title'], 200)}", evidence_ids=ids))
    for event in timeline:
        if event["kind"] in FACT_EVENT_KINDS and event["origin"] == "observed" and event["evidence_ids"]:
            facts.append(Fact(statement=clip(f"{event['title']}. {event.get('detail', '')}", 420), evidence_ids=event["evidence_ids"][:5]))
    return facts[:10]


def build_rule_hypotheses(incident: dict[str, Any], timeline: list[dict[str, Any]], first_error_by_service: dict[str, int]) -> list[Hypothesis]:
    hypotheses: list[Hypothesis] = []
    warn = next((e for e in timeline if e["kind"] == "early_warning"), None)
    if warn:
        hypotheses.append(Hypothesis(
            statement="Pressure may have been building before the first error.", origin="rule", strength="moderate",
            reasoning=f"{warn['title']}. Warnings that come first are often early signs, but their order alone does not prove they caused the errors.",
            evidence_ids=warn["evidence_ids"][:5]))
    if len(first_error_by_service) >= 2:
        hypotheses.append(Hypothesis(
            statement="A dependency shared by the affected services may be involved.", origin="rule", strength="weak",
            reasoning=f"Error-level records appear in {len(first_error_by_service)} services ({', '.join(first_error_by_service)}) inside one incident window. "
                      "Services that fail together often share a database, cache or network path, but they can also fail separately.",
            evidence_ids=list(first_error_by_service.values())[:5]))
    quiet = next((e for e in timeline if e["kind"] == "quiet_after"), None)
    if quiet and quiet["evidence_ids"]:
        hypotheses.append(Hypothesis(
            statement=f"The incident may have ended after {quiet['title'].rsplit(' ', 1)[-1]}.", origin="rule", strength="weak",
            reasoning="No error-level records follow in this file. The logs alone cannot confirm that the service recovered.",
            evidence_ids=quiet["evidence_ids"]))
    return hypotheses


def build_limitations(*, no_source: bool, used_ai: bool, ai_error: str | None, ai_configured: bool) -> list[str]:
    notes = [
        "Incidents are found from timing and message wording. This does not establish a root cause.",
        "Hypotheses are not confirmed causes. Check them against the evidence before acting.",
        "Only the records in the uploaded file were considered. Metrics, traces and recent changes were not available.",
        "This application never runs commands or changes any system. Every step is a check for a person to do.",
    ]
    if no_source:
        notes.append("No relevant runbook section was found, so no documented guidance is shown for this incident.")
    if used_ai:
        notes.append("The AI narrative and AI hypotheses were written by a language model and may be wrong. Records sent to it were clipped and redacted.")
    elif ai_error:
        notes.append(f"The AI provider could not be used ({ai_error}). The summary above is the non-AI version.")
    elif not ai_configured:
        notes.append("No AI provider is configured, so this is the non-AI version of the summary.")
    return notes


def retrieved_points(hits: list[dict[str, Any]]) -> list[RetrievedPoint]:
    return [RetrievedPoint(citation=h["citation"], document_id=h["document_id"], chunk_id=h["chunk_id"], relevance=h["relevance"],
                           text=clip(h["text"], 700)) for h in hits]
