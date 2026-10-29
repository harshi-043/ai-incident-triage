"""
Build incident summaries and answer questions about an incident.

The non-AI path always works. The AI path is optional, runs only when the user asks for it, and can never replace the
non-AI facts: it can add a narrative, hypotheses and checks, and each of those is validated before it is shown.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai import diagnostics, summary as det
from app.ai.evidence import EvidencePackage, build_package
from app.ai.prompts import answer_messages, summary_messages
from app.ai.providers import Provider, ProviderError, ai_configuration_problem, make_provider, parse_json_object
from app.ai.safety import clip, looks_like_change
from app.ai.schemas import DiagnosticStep, Hypothesis, LLMAnswer, LLMSummary, NotSuggested, SummaryOut
from app.core.config import Settings
from app.ingestion.normalize import iso_z
from app.models.tables import ErrorGroup, Incident, IncidentSummary, RunbookChunk, RunbookDocument
from app.rag.retriever import KnowledgeIndex
from app.repositories import incidents as repo
from app.repositories import logs as log_repo
from app.services import knowledge_service

logger = logging.getLogger("triage")
CANDIDATE_ERRORS, CANDIDATE_WARNINGS = 60, 30


# ---------------------------------------------------------------------------------------------------------------------
def _context(session: Session, incident: Incident) -> dict[str, Any]:
    """Everything the summary needs from the database, as plain dictionaries."""
    info = repo.incident_to_dict(incident)
    info["detection"] = {k: v for k, v in incident.detection.items() if k != "related"}
    groups = [g for g in (session.get(ErrorGroup, gid) for gid in incident.group_ids) if g is not None]
    group_samples = {g.id: list(g.sample_record_ids) for g in groups}

    ids: list[int] = []
    for event in incident.timeline:
        ids.extend(event.get("evidence_ids", []))
    for sample in group_samples.values():
        ids.extend(sample[:3])
    errors, _ = repo.incident_records(session, incident.id, levels=["ERROR", "CRITICAL"], service=None, q=None, page=1, page_size=CANDIDATE_ERRORS)
    warnings, _ = repo.incident_records(session, incident.id, levels=["WARNING"], service=None, q=None, page=1, page_size=CANDIDATE_WARNINGS)
    first_error_by_service: dict[str, int] = {}
    for service in incident.services:
        first, _ = repo.incident_records(session, incident.id, levels=["ERROR", "CRITICAL"], service=service, q=None, page=1, page_size=1)
        if first:
            first_error_by_service[service] = first[0].id
    rows = {r.id: r for r in [*errors, *warnings]}
    for r in log_repo.get_records_by_ids(session, sorted(set(ids) | set(first_error_by_service.values()))):
        rows[r.id] = r
    records = sorted((log_repo.record_to_dict(r) for r in rows.values()), key=lambda r: (r["timestamp"] or "", r["id"]))
    return {"info": info, "timeline": incident.timeline, "records": records, "group_samples": group_samples,
            "first_error_by_service": first_error_by_service}


def _diagnostic_sections(session: Session, hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The 'diagnostic steps' sections of the (up to) two best-matching runbooks."""
    sections: list[dict[str, Any]] = []
    seen: list[str] = []
    for hit in hits:
        if hit["document_id"] in seen:
            continue
        seen.append(hit["document_id"])
        if len(seen) > 2:
            break
        doc = session.get(RunbookDocument, hit["document_id"])
        if doc is None:
            continue
        chunks = list(session.scalars(select(RunbookChunk).where(RunbookChunk.document_id == doc.id).order_by(RunbookChunk.ordinal)))
        symptom = ""
        for c in chunks:
            if "symptom" in c.heading.lower():
                first_bullet = next((ln.strip()[2:] for ln in c.text.splitlines() if ln.strip().startswith(("- ", "* "))), "")
                symptom = clip(first_bullet, 200)
                break
        for c in chunks:
            if "diagnostic" in c.heading.lower():
                tail = c.heading.split(" > ", 1)[-1]
                sections.append({"citation": f"{doc.filename} › {tail}", "relevance": hit["relevance"], "text": c.text, "symptom": symptom})
    return sections


def _window(info: dict[str, Any]) -> str:
    return f"{info['first_seen']} to {info['last_seen']}"


# ---------------------------------------------------------------------------------------------------------------------
def build_summary(session: Session, settings: Settings, kb: KnowledgeIndex, incident: Incident, *, use_ai: bool,
                  provider: Provider | None) -> SummaryOut:
    ctx = _context(session, incident)
    info, timeline, records = ctx["info"], ctx["timeline"], ctx["records"]
    query = knowledge_service.incident_search_query(session, incident)
    retrieval = kb.search(session, settings, query, top_k=4, min_relevance=settings.min_relevance)
    hits = retrieval["results"]

    fallback_ids = (next((e["evidence_ids"] for e in timeline if e["kind"] == "first_error"), []) or [r["id"] for r in records[:2]])
    sections = _diagnostic_sections(session, hits)
    runbook_steps, rejected = diagnostics.steps_from_runbooks(sections, records, fallback_ids, _window(info))
    rule = diagnostics.rule_steps(info, timeline, records, [{"citation": h["citation"], "relevance": h["relevance"], "text": h["text"]} for h in hits])
    hypotheses: list[Hypothesis] = det.build_rule_hypotheses(info, timeline, ctx["first_error_by_service"])
    steps = [*rule, *runbook_steps]

    narrative: str | None = None
    headline = det.build_headline(info)
    ai_error = None
    used_ai = False
    config_problem = ai_configuration_problem(settings)
    ai_available = provider is not None
    if use_ai:
        if provider is None:
            ai_error = config_problem or "No AI provider is configured (AI_PROVIDER=none)."
        else:
            try:
                package = build_package({"id": info["label"], "severity": info["severity"], "window": _window(info),
                                         "services": ", ".join(info["services"]), "error_records": info["error_count"]},
                                        records, timeline, hits, max_records=settings.ai_max_evidence_records)
                ai = _ask_model_for_summary(provider, package)
                new_h, new_s, new_rejected, narrative_ok = _validate_ai_summary(ai, package, window=_window(info))
                if not new_h and not new_s:
                    raise ProviderError("ai_invalid_output", "No suggestion from the AI cited valid evidence, so none were used.")
                hypotheses += new_h
                steps += new_s
                rejected += new_rejected
                if narrative_ok:
                    narrative = ai.narrative
                headline = headline  # the headline stays the computed one; the model's headline is not used as fact
                used_ai = True
            except ProviderError as exc:
                ai_error = exc.message
                logger.warning("AI summary failed (%s); using the non-AI summary.", exc.code)

    summary = SummaryOut(
        incident_id=incident.id, incident_label=info["label"], generated_by=(f"{provider.name}:{settings.ai_model}" if used_ai and provider else "deterministic"),
        used_ai=used_ai, ai_error=ai_error, ai_available=ai_available, headline=headline, ai_narrative=narrative,
        facts=det.build_facts(info, timeline, ctx["group_samples"]), retrieved=det.retrieved_points(hits),
        no_relevant_source=retrieval["no_relevant_source"], hypotheses=hypotheses, steps=diagnostics.number_steps(steps),
        not_suggested=rejected, limitations=det.build_limitations(no_source=retrieval["no_relevant_source"], used_ai=used_ai, ai_error=ai_error,
                                                                  ai_configured=config_problem is None and settings.ai_provider != "none"),
        created_at=iso_z(datetime.now(timezone.utc).replace(tzinfo=None)))
    return summary


def _ask_model_for_summary(provider: Provider, package: EvidencePackage) -> LLMSummary:
    system, user, _ = summary_messages(package)
    obj = parse_json_object(provider.complete(system, user))
    try:
        return LLMSummary.model_validate(obj)
    except ValidationError:
        raise ProviderError("ai_invalid_output", "The AI answer did not match the required format.") from None


def _validate_ai_summary(ai: LLMSummary, package: EvidencePackage, *, window: str
                         ) -> tuple[list[Hypothesis], list[DiagnosticStep], list[NotSuggested], bool]:
    """Keep only model output that cites real records; move anything that looks like a change out of the suggestions."""
    valid = package.valid_record_ids
    hypotheses: list[Hypothesis] = []
    for h in ai.hypotheses:
        ids = [i for i in h.evidence_ids if i in valid]
        if ids:
            hypotheses.append(Hypothesis(statement=h.statement, reasoning=h.reasoning, origin="ai_hypothesis", strength="weak", evidence_ids=ids,
                                         caveat="Written by an AI model. It may be wrong. Check it against the cited records."))
    steps: list[DiagnosticStep] = []
    rejected: list[NotSuggested] = []
    for s in ai.steps:
        ids = [i for i in s.evidence_ids if i in valid]
        if not ids:
            continue
        reason = looks_like_change(f"{s.title}. {s.instruction}")
        if reason:
            rejected.append(NotSuggested(text=clip(s.instruction, 300), reason=f"The AI suggested something that reads like a change ('{reason}'), so it is not shown as a step.",
                                         origin="ai_hypothesis"))
            continue
        steps.append(DiagnosticStep(id="", title=s.title, instruction=s.instruction, origin="ai_hypothesis", strength="weak",
                                    strength_reason="Suggested by an AI model only; no runbook or rule backs it.", evidence_ids=ids,
                                    evidence_match="specific", citation=None, expected_observation=s.expected_observation))
    narrative_reason = looks_like_change(ai.narrative)
    if narrative_reason:
        rejected.append(NotSuggested(text=clip(ai.narrative, 300), reason=f"The AI narrative contains wording that reads like a change ('{narrative_reason}'), so it is not shown.",
                                     origin="ai_hypothesis"))
    return hypotheses, steps, rejected, narrative_reason is None


# ---------------------------------------------------------------------------------------------------------------------
def save_summary(session: Session, incident: Incident, summary: SummaryOut) -> None:
    session.add(IncidentSummary(incident_id=incident.id, provider=summary.generated_by.split(":")[0],
                                used_fallback=bool(summary.ai_error), payload=summary.model_dump()))
    repo.add_activity(session, incident.id, "summary", f"Summary generated ({'with AI' if summary.used_ai else 'without AI'})")
    session.commit()


def latest_summary(session: Session, incident_id: str) -> dict[str, Any] | None:
    row = session.scalar(select(IncidentSummary).where(IncidentSummary.incident_id == incident_id).order_by(IncidentSummary.id.desc()))
    return row.payload if row else None


# ---------------------------------------------------------------------------------------------------------------------
def answer_question(session: Session, settings: Settings, kb: KnowledgeIndex, incident: Incident, question: str, *, use_ai: bool,
                    provider: Provider | None) -> dict[str, Any]:
    """Find the log records and runbook sections that relate to a question. Optionally let the AI phrase an answer from them."""
    ctx = _context(session, incident)
    wanted = diagnostics.tokens(question)
    scored = []
    for r in ctx["records"]:
        overlap = len(wanted & diagnostics.tokens(f"{r['message']} {r['service']} {r.get('exception_type') or ''} {r.get('endpoint') or ''}"))
        if overlap:
            scored.append((-overlap, r["timestamp"] or "", r["id"], r))
    scored.sort(key=lambda x: x[:3])
    matches = [row[3] for row in scored[:6]]
    retrieval = kb.search(session, settings, question, top_k=3, min_relevance=settings.min_relevance)
    hits = retrieval["results"]

    if matches or hits:
        text = (f"Found {len(matches)} log record(s) and {len(hits)} runbook section(s) that match your question. "
                "This is search output, not an AI answer: read the cited records and sections.")
    else:
        text = "No log record in this incident and no runbook section matches your question."
    result: dict[str, Any] = {
        "question": question, "answer": text, "answer_origin": "retrieval", "used_ai": False, "ai_error": None,
        "evidence": [{"id": r["id"], "timestamp": r["timestamp"], "level": r["level"], "service": r["service"], "message": clip(r["message"], 300)} for r in matches],
        "runbook_sources": [{"citation": h["citation"], "relevance": h["relevance"], "text": clip(h["text"], 500)} for h in hits],
        "no_relevant_source": retrieval["no_relevant_source"], "uncertainty": None,
    }
    if use_ai:
        if provider is None:
            result["ai_error"] = ai_configuration_problem(settings) or "No AI provider is configured (AI_PROVIDER=none)."
            return result
        try:
            info = ctx["info"]
            package = build_package({"id": info["label"], "severity": info["severity"], "window": _window(info),
                                     "services": ", ".join(info["services"]), "error_records": info["error_count"]},
                                    ctx["records"], ctx["timeline"], hits, max_records=settings.ai_max_evidence_records)
            system, user, _ = answer_messages(package, question)
            try:
                ai = LLMAnswer.model_validate(parse_json_object(provider.complete(system, user)))
            except ValidationError:
                raise ProviderError("ai_invalid_output", "The AI answer did not match the required format.") from None
            ids = [i for i in ai.evidence_ids if i in package.valid_record_ids]
            if not ids:
                raise ProviderError("ai_invalid_output", "The AI answer cited no valid evidence, so it was not used.")
            reason = looks_like_change(ai.answer)
            if reason:
                raise ProviderError("ai_invalid_output", f"The AI answer contained wording that reads like a change ('{reason}'), so it was not used.")
            result.update({"answer": ai.answer, "answer_origin": "ai_hypothesis", "used_ai": True, "uncertainty": ai.uncertainty or None,
                           "evidence": [e for e in result["evidence"] if e["id"] in ids] or
                                       [{"id": r["id"], "timestamp": r["timestamp"], "level": r["level"], "service": r["service"], "message": clip(r["message"], 300)}
                                        for r in ctx["records"] if r["id"] in ids]})
        except ProviderError as exc:
            result["ai_error"] = exc.message
    return result
