import type { Strength } from "../api/types";
import { Badge, OriginBadge } from "./ui/Badge";
import { CommandBlock } from "./CommandBlock";

const TONE: Record<Strength, "ok" | "info" | "neutral"> = { strong: "ok", moderate: "info", weak: "neutral" };

/** One retrieved runbook section: its citation, how well it matched, and its text as quoted. */
export function RunbookHitCard({ citation, relevance, text, commands = [] }: {
  citation: string;
  relevance: Strength;
  text: string;
  commands?: string[];
}) {
  return (
    <article className="rounded-lg border border-line bg-surface p-3">
      <header className="flex flex-wrap items-center gap-2">
        <OriginBadge origin="runbook" />
        <h4 className="min-w-0 break-words text-sm font-semibold text-ink">{citation}</h4>
        <Badge tone={TONE[relevance]} title="How closely this section matches the incident. A guide, not a probability.">
          {relevance.charAt(0).toUpperCase() + relevance.slice(1)} match
        </Badge>
      </header>
      <p className="mt-2 whitespace-pre-wrap break-words text-sm text-ink">{text}</p>
      <CommandBlock commands={commands} />
    </article>
  );
}
