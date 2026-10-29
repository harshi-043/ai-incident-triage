import { Bot, ShieldCheck } from "lucide-react";
import type { Summary } from "../api/types";
import { formatTime } from "../lib/format";
import { CommandBlock } from "./CommandBlock";
import { EvidenceChips } from "./EvidenceChips";
import { RunbookHitCard } from "./RunbookHitCard";
import { Badge, OriginBadge, StrengthBadge } from "./ui/Badge";
import { Card, CardHeader } from "./ui/Card";
import { Note } from "./ui/States";

/**
 * The four kinds of content are kept in four separate sections on purpose:
 *   1 facts read from the logs, 2 quoted runbook text, 3 hypotheses, 4 read-only checks.
 * Every item carries a badge that says where it came from.
 */
export function SummaryView({ summary }: { summary: Summary }) {
  return (
    <div className="space-y-5">
      <Card>
        <div className="flex flex-wrap items-center gap-2">
          <Badge tone={summary.used_ai ? "info" : "neutral"}>{summary.used_ai ? `AI-assisted (${summary.generated_by})` : "Computed without AI"}</Badge>
          <span className="text-xs text-muted">Generated {formatTime(summary.created_at, false)} UTC</span>
        </div>
        <h2 className="mt-2 break-words text-lg font-semibold text-ink">{summary.headline}</h2>
        {summary.ai_error && (
          <div className="mt-3"><Note tone="warn">The AI provider could not be used: {summary.ai_error} The summary below is the version without AI.</Note></div>
        )}
        {summary.ai_narrative && (
          <div className="mt-3 rounded-lg border border-origin-ai/30 bg-origin-ai-bg p-3">
            <p className="flex items-center gap-2 text-xs font-medium text-origin-ai"><Bot className="h-4 w-4" aria-hidden /> AI narrative. Written by a language model, it may be wrong.</p>
            <p className="mt-1 whitespace-pre-wrap text-sm text-ink">{summary.ai_narrative}</p>
          </div>
        )}
      </Card>

      <Card>
        <CardHeader title="1. Facts from the logs" subtitle="Read directly from the log records. Click a record number to check it yourself." />
        {summary.facts.length === 0 ? <p className="text-sm text-muted">No facts could be drawn from this incident.</p> : (
          <ul className="space-y-3">
            {summary.facts.map((fact, i) => (
              <li key={i} className="text-sm">
                <div className="flex flex-wrap items-start gap-2"><OriginBadge origin="observed" /><span className="min-w-0 flex-1 break-words text-ink">{fact.statement}</span></div>
                <div className="mt-1 pl-1"><EvidenceChips ids={fact.evidence_ids} /></div>
              </li>
            ))}
          </ul>
        )}
      </Card>

      <Card>
        <CardHeader title="2. Runbook text found" subtitle="Quoted from the knowledge base, with its source. It was written by other people and is not a statement about this incident." />
        {summary.no_relevant_source ? (
          <Note tone="warn">No relevant source was found in the knowledge base for this incident, so no documented guidance is shown. The checks in section 4 come only from what was observed.</Note>
        ) : (
          <div className="space-y-3">{summary.retrieved.map((r) => <RunbookHitCard key={r.chunk_id} citation={r.citation} relevance={r.relevance} text={r.text} />)}</div>
        )}
      </Card>

      <Card>
        <CardHeader title="3. Hypotheses (not confirmed)" subtitle="Possible explanations to check. None of them is a confirmed cause." />
        {summary.hypotheses.length === 0 ? <p className="text-sm text-muted">No hypotheses were produced.</p> : (
          <ul className="space-y-4">
            {summary.hypotheses.map((h, i) => (
              <li key={i} className="text-sm">
                <div className="flex flex-wrap items-center gap-2"><OriginBadge origin={h.origin} /><StrengthBadge strength={h.strength} /></div>
                <p className="mt-1 break-words font-medium text-ink">{h.statement}</p>
                <p className="break-words text-muted">{h.reasoning}</p>
                <div className="mt-1"><EvidenceChips ids={h.evidence_ids} /></div>
                <p className="mt-1 text-xs text-muted">{h.caveat}</p>
              </li>
            ))}
          </ul>
        )}
      </Card>

      <Card>
        <CardHeader title="4. Suggested checks (read-only)" subtitle="Things a person can look at. Nothing here changes a system, and this application does not run any of it." />
        {summary.steps.length === 0 ? <p className="text-sm text-muted">No checks were produced.</p> : (
          <ol className="space-y-4">
            {summary.steps.map((step, index) => (
              <li key={step.id} className="rounded-lg border border-line p-3">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-mono text-xs text-muted">{index + 1}.</span>
                  <h3 className="min-w-0 break-words text-sm font-semibold text-ink">{step.title}</h3>
                  <OriginBadge origin={step.origin} />
                  <StrengthBadge strength={step.strength} reason={step.strength_reason} />
                </div>
                <p className="mt-1 break-words text-sm text-ink">{step.instruction}</p>
                <p className="mt-1 break-words text-sm text-muted"><span className="font-medium text-ink">What you would expect to see:</span> {step.expected_observation}</p>
                <p className="mt-1 text-xs text-muted">{step.strength_reason}</p>
                {step.citation && <p className="mt-1 text-xs text-muted">Source: <span className="font-medium text-origin-runbook">{step.citation}</span></p>}
                <div className="mt-1">
                  <EvidenceChips ids={step.evidence_ids} label={step.evidence_match === "specific" ? "Related records" : "Starting point"} />
                  {step.evidence_match === "general" && <span className="ml-2 text-xs text-muted">(no record matches this check in particular)</span>}
                </div>
                <CommandBlock commands={step.documented_commands} />
              </li>
            ))}
          </ol>
        )}
      </Card>

      {summary.not_suggested.length > 0 && (
        <Card>
          <CardHeader title="Mentioned but not suggested" subtitle="These read like changes to a system. They are listed so you know they exist, and are not recommended by this tool." />
          <ul className="space-y-2 text-sm">
            {summary.not_suggested.map((n, i) => (
              <li key={i}><OriginBadge origin={n.origin} /> <span className="break-words text-ink">{n.text}</span> <span className="text-muted">{n.reason}</span></li>
            ))}
          </ul>
        </Card>
      )}

      <Card>
        <CardHeader title="Limits of this summary" />
        <ul className="list-disc space-y-1 pl-5 text-sm text-muted">{summary.limitations.map((l, i) => <li key={i}>{l}</li>)}</ul>
        <p className="mt-3 flex items-center gap-2 text-sm font-medium text-ocean-800"><ShieldCheck className="h-4 w-4" aria-hidden /> {summary.notice}</p>
      </Card>
    </div>
  );
}
