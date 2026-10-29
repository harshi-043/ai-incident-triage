"""
Read-only diagnostic steps.

Steps come from three places, and each says which one (`origin`):
    runbook        a step written in a retrieved runbook (shown with its citation)
    rule           a fixed rule in this code that looks at what was observed in the incident
    ai_hypothesis  a suggestion from the optional AI model (checked before it is shown)

A step is never run by this application. Anything that looks like a change to a system is moved to `not_suggested`.
"""
from __future__ import annotations

import re
from typing import Any

from app.ai.safety import clip, looks_like_change
from app.ai.schemas import DiagnosticStep, NotSuggested, Strength

_STOP = {
    "this", "that", "with", "from", "they", "them", "then", "than", "have", "been", "were", "what", "when", "where", "which",
    "check", "compare", "look", "whether", "there", "their", "into", "does", "other", "about", "after", "before", "during",
    "incident", "window", "records", "record", "error", "errors", "service", "services", "same", "should", "would", "could",
    "also", "only", "each", "some", "many", "most", "more", "less", "time", "times", "show", "shows", "start", "started",
}
_ITEM = re.compile(r"^\s*(?:\d+[.)]|[-*])\s+(.*\S)\s*$")
_WORD = re.compile(r"[A-Za-z][A-Za-z0-9_.\-]{3,}")
MIN_OVERLAP = 2  # a single shared word is too weak to call a record "specific" evidence or a runbook "corroboration"


def tokens(text: str) -> set[str]:
    return {w.lower() for w in _WORD.findall(text or "") if w.lower() not in _STOP}


def link_evidence(text: str, records: list[dict[str, Any]], fallback_ids: list[int], limit: int = 3) -> tuple[list[int], str]:
    """Pick the records whose wording overlaps the step most. Returns (ids, "specific"|"general")."""
    wanted = tokens(text)
    scored: list[tuple[int, str, int]] = []
    for r in records:
        haystack = tokens(f"{r.get('message', '')} {r.get('service', '')} {r.get('exception_type') or ''} {r.get('endpoint') or ''}")
        overlap = len(wanted & haystack)
        if overlap >= MIN_OVERLAP:
            scored.append((-overlap, r.get("timestamp") or "", r["id"]))
    if scored:
        scored.sort()
        return [rid for _, _, rid in scored[:limit]], "specific"
    return fallback_ids[:limit], "general"


def _strength_for_runbook(relevance: str, match: str) -> tuple[Strength, str]:
    if relevance == "weak":
        return "weak", "The runbook section is only a weak match for this incident."
    if match == "specific":
        return "strong", f"The runbook section is a {relevance} match and log records mention the same things this check looks at."
    return "moderate", f"The runbook section is a {relevance} match, but no log record matches this particular check."


def steps_from_runbooks(sections: list[dict[str, Any]], records: list[dict[str, Any]], fallback_ids: list[int],
                        window: str) -> tuple[list[DiagnosticStep], list[NotSuggested]]:
    """
    `sections` are diagnostic-steps chunks of the best-matching runbooks, each with: citation, relevance, text and an optional
    `symptom` line from the same document. Numbered or bulleted items become steps; fenced commands become one text-only step.
    """
    steps: list[DiagnosticStep] = []
    rejected: list[NotSuggested] = []
    for section in sections:
        in_fence, commands, items = False, [], []
        for line in section["text"].splitlines():
            if line.strip().startswith(("```", "~~~")):
                in_fence = not in_fence
            elif in_fence:
                if line.strip():
                    commands.append(line.strip())
            elif (m := _ITEM.match(line)):
                items.append(m.group(1))
        expected = (f"Compare what you find with the incident window {window}. "
                    + (f"The runbook describes this problem as: {section['symptom']}" if section.get("symptom") else
                       "The runbook's own symptom list describes what to look for."))
        for item in items:
            reason = looks_like_change(item)
            if reason:
                rejected.append(NotSuggested(text=clip(item, 300), reason=f"Reads like a change to a system ('{reason}'), so it is not suggested.",
                                             citation=section["citation"], origin="runbook"))
                continue
            ids, match = link_evidence(item, records, fallback_ids)
            strength, why = _strength_for_runbook(section["relevance"], match)
            steps.append(DiagnosticStep(
                id="", title=clip(item.split(".")[0].split(":")[0], 90), instruction=clip(item, 400), origin="runbook", strength=strength,
                strength_reason=why, evidence_ids=ids, evidence_match=match, citation=section["citation"], expected_observation=expected))
        safe_commands = []
        for command in commands:
            reason = looks_like_change(command)
            if reason:
                rejected.append(NotSuggested(text=clip(command, 200), reason=f"Command reads like a change ('{reason}'), so it is not suggested.",
                                             citation=section["citation"], origin="runbook"))
            else:
                safe_commands.append(command)
        if safe_commands:
            strength, why = _strength_for_runbook(section["relevance"], "general")
            steps.append(DiagnosticStep(
                id="", title="Example commands from the runbook (for a human to review)",
                instruction="The runbook lists these read-only example commands. They are shown as text. This application does not run them.",
                origin="runbook", strength=strength, strength_reason=why, evidence_ids=fallback_ids[:2], evidence_match="general",
                citation=section["citation"], expected_observation=f"Compare the output with the incident window {window}.",
                documented_commands=safe_commands[:10]))
    return steps, rejected


def rule_steps(incident: dict[str, Any], timeline: list[dict[str, Any]], records: list[dict[str, Any]],
               corroboration: list[dict[str, Any]]) -> list[DiagnosticStep]:
    """Steps that follow directly from what was observed. `corroboration` are retrieved runbook sections used to raise strength."""
    by_kind: dict[str, list[dict[str, Any]]] = {}
    for event in timeline:
        by_kind.setdefault(event["kind"], []).append(event)
    detection = incident.get("detection", {})
    out: list[DiagnosticStep] = []

    def add(title: str, instruction: str, expected: str, ids: list[int], keywords: set[str]) -> None:
        if not ids:
            return
        citation, why = None, "Based directly on the observed records."
        strength: Strength = "moderate"
        for section in corroboration:
            if section["relevance"] != "weak" and len(keywords & tokens(section["text"])) >= MIN_OVERLAP:
                strength, citation = "strong", section["citation"]
                why = "Based on the observed records, and a retrieved runbook section covers the same subject."
                break
        out.append(DiagnosticStep(id="", title=title, instruction=clip(instruction, 400), origin="rule", strength=strength, strength_reason=why,
                                  evidence_ids=ids[:5], evidence_match="specific", citation=citation, expected_observation=clip(expected, 300)))

    first = by_kind.get("first_error", [])
    if first:
        add("Read the first error records and their stack traces",
            f"Open the earliest error-level records (see the evidence links) from {first[0]['title'].split(':', 1)[-1].strip()} and read the message "
            "and the stack trace to see which call failed first.",
            "The earliest error names the component that failed first. Later errors may be follow-on effects of it.",
            first[0]["evidence_ids"], tokens(first[0]["title"] + " " + first[0].get("detail", "")))
    warn = by_kind.get("early_warning", [])
    if warn:
        add("Check the metric that the early warnings describe",
            f"The log shows warnings before the first error ({warn[0]['detail'][:160]}). Look at that metric over the hour before the incident.",
            "If pressure built up, the same metric will be rising or near its limit before the first error.",
            warn[0]["evidence_ids"], tokens(warn[0].get("detail", "")))
    five = by_kind.get("http_5xx", [])
    if five:
        codes = ", ".join(sorted(detection.get("status_codes", {}).keys())) or "5xx"
        ids = [r["id"] for r in records if (r.get("http_status") or 0) >= 500][:5] or five[0]["evidence_ids"]
        add(f"Find which endpoints returned HTTP {codes}",
            f"Group the HTTP {codes} responses by endpoint and by upstream service to see whether one route or one backend is behind them.",
            "Most of the failing responses point to one endpoint or one upstream service.", ids, {"5xx", "500", "502", "503", "504", "upstream"})
    slow = by_kind.get("latency_threshold", [])
    if slow:
        base = detection.get("baseline_latency_ms")
        add("Compare request durations before and during the incident",
            "Plot request durations for the affected endpoints across the incident window and the hour before it.",
            (f"Durations were about {base:,.0f} ms at baseline and rise during the incident." if base else "Durations rise during the incident."),
            slow[0]["evidence_ids"], {"latency", "slow", "duration", "response"})
    services = incident.get("services", [])
    if len(services) >= 2:
        firsts: dict[str, int] = {}
        for r in records:
            if r["level"] in ("ERROR", "CRITICAL") and r["service"] not in firsts:
                firsts[r["service"]] = r["id"]
        add("Check what the affected services have in common",
            f"{', '.join(services[:5])} all report errors. Check whether they share a database, cache, network path or release.",
            "A shared dependency would show errors or slow responses in the same minutes for all of them.",
            list(firsts.values()), {"database", "shared", "dependency", "network"})
    ctx = by_kind.get("context_event", [])
    if ctx:
        add("Check the event logged near the start of the incident",
            f"The log reports an event close to the start: {ctx[0]['detail'][:200]}. Check whether it relates to the failure (the log shows timing only).",
            "If it is related, the first symptoms appear shortly after it and not before.", ctx[0]["evidence_ids"], tokens(ctx[0].get("detail", "")))
    return out


def number_steps(steps: list[DiagnosticStep]) -> list[DiagnosticStep]:
    """Drop repeats (same title) and give each step a stable id. Order: strong first, then moderate, then weak; rule before runbook."""
    rank = {"strong": 0, "moderate": 1, "weak": 2}
    origin_rank = {"rule": 0, "runbook": 1, "ai_hypothesis": 2}
    seen: set[str] = set()
    unique: list[DiagnosticStep] = []
    for step in sorted(steps, key=lambda s: (rank[s.strength], origin_rank[s.origin])):
        key = re.sub(r"\W+", " ", step.title.lower()).strip()
        if key in seen:
            continue
        seen.add(key)
        unique.append(step)
    for i, step in enumerate(unique, 1):
        step.id = f"step-{i}"
    return unique
