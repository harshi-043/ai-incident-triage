"""
Incident detection with transparent rules.

An incident is a burst of error-level records. The rules, in plain words:

  1. Take every error-level record that has a timestamp. Error-level means ERROR, CRITICAL or an HTTP 5xx.
  2. Sort them by time. A gap longer than `gap_minutes` between two errors starts a new burst.
  3. Keep a burst only if some `gap_minutes`-long window inside it holds at least `min_errors` errors.
  4. Attach warning patterns whose records are concentrated in the burst (so routine background
     warnings are not pulled in), and INFO lines about deployments, restarts, failovers and recoveries.
  5. Rate the severity with the fixed thresholds in `rate_severity`.

Every incident stores the numbers that created it, so a person can see why it exists.
Nothing here decides a root cause: the output is a time-bounded set of related log records.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta

from app.incident.timeline import build_timeline, is_context_event, median_latency
from app.incident.types import DetectionParams, Group, IncidentDraft, Rec

# Severity thresholds, shown to the user in the incident explanation.
CRITICAL_ERRORS, CRITICAL_SERVICES = 100, 3
HIGH_ERRORS, HIGH_SERVICES = 40, 3
MEDIUM_ERRORS = 15


def _peak_window(errors: list[Rec], window: timedelta) -> tuple[int, datetime]:
    """The largest number of errors inside any window of the given length, and where that window starts."""
    best, best_start, left = 0, errors[0].ts, 0
    for right, record in enumerate(errors):
        while record.ts - errors[left].ts > window:
            left += 1
        if right - left + 1 > best:
            best, best_start = right - left + 1, errors[left].ts
    return best, best_start


def rate_severity(errors: list[Rec], services: list[str], has_critical: bool) -> tuple[str, str]:
    """Return (severity, the rule that applied)."""
    n, s = len(errors), len(services)
    five_xx = sum(1 for r in errors if r.http_status and r.http_status >= 500)
    if has_critical:
        return "critical", "a CRITICAL-level record is part of the incident"
    if n >= CRITICAL_ERRORS and s >= CRITICAL_SERVICES:
        return "critical", f"{n} error-level records across {s} services (critical needs at least {CRITICAL_ERRORS} across {CRITICAL_SERVICES})"
    if n >= HIGH_ERRORS:
        return "high", f"{n} error-level records (high needs at least {HIGH_ERRORS})"
    if s >= HIGH_SERVICES:
        return "high", f"{s} services reported errors (high needs at least {HIGH_SERVICES})"
    if n >= 20 and five_xx / n >= 0.3:
        return "high", f"{five_xx} of {n} errors are HTTP 5xx responses (at least 30% with 20 or more errors)"
    if n >= MEDIUM_ERRORS:
        return "medium", f"{n} error-level records (medium needs at least {MEDIUM_ERRORS})"
    return "low", f"{n} error-level records (below the medium threshold of {MEDIUM_ERRORS})"


def detect_incidents(
    records: list[Rec], groups: list[Group], params: DetectionParams,
) -> tuple[list[IncidentDraft], list[Group]]:
    """Return the incidents (oldest first) and the error groups that did not become part of any incident."""
    gap = timedelta(minutes=params.gap_minutes)
    errors = sorted((r for r in records if r.is_error and r.ts is not None), key=lambda r: (r.ts, r.id))

    bursts: list[list[Rec]] = []
    for record in errors:
        if bursts and record.ts - bursts[-1][-1].ts <= gap:
            bursts[-1].append(record)
        else:
            bursts.append([record])

    baseline_latency = median_latency(records)
    context_candidates = [r for r in records if r.ts is not None and is_context_event(r)]
    drafts: list[IncidentDraft] = []

    for burst in bursts:
        peak, peak_start = _peak_window(burst, gap)
        if peak < params.min_errors:
            continue
        window_start = burst[0].ts - timedelta(minutes=params.lead_minutes)
        window_end = burst[-1].ts + timedelta(minutes=params.lag_minutes)
        burst_ids = {r.id for r in burst}

        # Warning patterns that are concentrated inside this window.
        attached_groups: list[Group] = []
        attached_warnings: list[Rec] = []
        for group in groups:
            warnings = [r for r in group.records if not r.is_error and r.id not in burst_ids]
            timed = [r for r in group.records if r.ts is not None]
            if not warnings or not timed:
                continue
            inside = [r for r in warnings if r.ts is not None and window_start <= r.ts <= window_end]
            if len(inside) >= 3 and len(inside) / len(timed) >= params.concentration:
                attached_groups.append(group)
                attached_warnings.extend(inside)

        services = sorted({r.service for r in burst} | {r.service for r in attached_warnings})
        context = [r for r in context_candidates
                   if window_start <= r.ts <= window_end and r.service in services]

        evidence = {r.id: r for r in [*burst, *attached_warnings, *context]}
        ordered = sorted(evidence.values(), key=lambda r: (r.ts is None, r.ts, r.id))
        incident_groups = [g for g in groups if any(r.id in evidence for r in g.records)]

        has_critical = any(r.level == "CRITICAL" for r in burst)
        severity, severity_rule = rate_severity(burst, sorted({r.service for r in burst}), has_critical)
        timeline = build_timeline(burst, attached_warnings, context, incident_groups, baseline_latency)

        in_incident = Counter()
        for g in incident_groups:
            in_incident[g.key] = sum(1 for r in g.records if r.id in evidence)
        top = sorted(incident_groups, key=lambda g: -in_incident[g.key])[:5]
        top_patterns = [{
            "group_key": g.key, "title": g.title, "template": g.template, "count": in_incident[g.key],
            "services": g.services, "method": g.method,
        } for g in top]

        statuses = Counter(r.http_status for r in burst if r.http_status)
        main = max((g for g in incident_groups if any(r.id in burst_ids for r in g.records)),
                   key=lambda g: sum(1 for r in g.records if r.id in burst_ids), default=None)
        title = main.title if main else f"{burst[0].service}: errors"
        if len(services) > 1:
            title = f"{title} (+{len(services) - 1} more service{'s' if len(services) > 2 else ''})"

        explanation = (
            f"Created because {len(burst)} error-level records occurred between {burst[0].ts:%H:%M:%S} and {burst[-1].ts:%H:%M:%S} "
            f"with no gap longer than {params.gap_minutes} minutes, and {peak} of them fell inside one {params.gap_minutes}-minute "
            f"window starting {peak_start:%H:%M:%S} (the minimum is {params.min_errors}). "
            f"Severity {severity}: {severity_rule}. "
        )
        if attached_groups:
            explanation += (f"{len(attached_groups)} warning pattern(s) were attached because at least "
                            f"{params.concentration:.0%} of their occurrences fall inside this period. ")
        explanation += "This groups records by time and wording. It does not establish a root cause."

        drafts.append(IncidentDraft(
            number=0, title=title[:290], severity=severity, first_seen=ordered[0].ts if ordered[0].ts else burst[0].ts,
            last_seen=burst[-1].ts, records=ordered, error_count=len(burst), services=services, groups=incident_groups,
            timeline=timeline, explanation=explanation, top_patterns=top_patterns,
            detection={
                "gap_minutes": params.gap_minutes, "min_errors": params.min_errors, "peak_window_errors": peak,
                "peak_window_start": peak_start.isoformat(), "error_records": len(burst),
                "attached_warning_records": len(attached_warnings), "context_events": len(context),
                "severity_rule": severity_rule, "status_codes": {str(k): v for k, v in statuses.most_common(6)},
                "window_start": window_start.isoformat(), "window_end": window_end.isoformat(),
                "baseline_latency_ms": baseline_latency,
            }))

    drafts.sort(key=lambda d: d.first_seen)
    for number, draft in enumerate(drafts, start=1):
        draft.number = number

    # Incidents that share an error pattern are related.
    for i, a in enumerate(drafts):
        for b in drafts[i + 1:]:
            b_keys = {g.key for g in b.groups}
            shared = [g for g in a.groups if g.key in b_keys]
            if shared:
                a.related_numbers.append(b.number)
                b.related_numbers.append(a.number)
                a.detection.setdefault("related", []).append({"number": b.number, "shared_patterns": [g.title for g in shared[:3]]})
                b.detection.setdefault("related", []).append({"number": a.number, "shared_patterns": [g.title for g in shared[:3]]})

    used = {r.id for d in drafts for r in d.records}
    isolated = [g for g in groups if g.error_count and not any(r.id in used for r in g.records if r.is_error)]
    return drafts, isolated
