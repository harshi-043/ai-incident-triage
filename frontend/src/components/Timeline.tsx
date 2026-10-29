import type { TimelineEvent } from "../api/types";
import { formatClock } from "../lib/format";
import { EvidenceChips } from "./EvidenceChips";
import { OriginBadge } from "./ui/Badge";

const DOT: Record<string, string> = {
  early_warning: "bg-warn", context_event: "bg-origin-rule", first_error: "bg-danger", http_5xx: "bg-danger", peak: "bg-danger",
  latency_threshold: "bg-orange", last_error: "bg-slate-500", quiet_after: "bg-ok",
};

/** The incident timeline, oldest first. Every event says whether it was observed or inferred and links to its records. */
export function Timeline({ events }: { events: TimelineEvent[] }) {
  if (events.length === 0) return <p className="text-sm text-muted">No timeline events.</p>;
  return (
    <ol className="relative space-y-4 border-l-2 border-line pl-5">
      {events.map((event, index) => (
        <li key={`${event.time}-${event.kind}-${index}`} className="relative">
          <span className={`absolute -left-[27px] top-1.5 h-3 w-3 rounded-full ring-4 ring-surface ${DOT[event.kind] ?? "bg-ocean-600"}`} aria-hidden />
          <div className="flex flex-wrap items-center gap-2">
            <time dateTime={event.time} className="font-mono text-xs tabular-nums text-muted">{formatClock(event.time)} UTC</time>
            <OriginBadge origin={event.origin} />
          </div>
          <p className="mt-0.5 text-sm font-medium text-ink">{event.title}</p>
          {event.detail && <p className="text-sm text-muted">{event.detail}</p>}
          <div className="mt-1"><EvidenceChips ids={event.evidence_ids} /></div>
        </li>
      ))}
    </ol>
  );
}
