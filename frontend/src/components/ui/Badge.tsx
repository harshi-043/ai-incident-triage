import type { ReactNode } from "react";
import { Bot, BookOpen, Eye, Ruler, Lightbulb } from "lucide-react";
import type { Origin, Severity, Status, Strength } from "../../api/types";

type Tone = "neutral" | "danger" | "orange" | "warn" | "ok" | "info";

const tones: Record<Tone, string> = {
  neutral: "bg-slate-100 text-ink",
  danger: "bg-danger-bg text-danger",
  orange: "bg-orange-bg text-orange",
  warn: "bg-warn-bg text-warn",
  ok: "bg-ok-bg text-ok",
  info: "bg-ocean-50 text-ocean-800",
};

export function Badge({ children, tone = "neutral", title }: { children: ReactNode; tone?: Tone; title?: string }) {
  return (
    <span title={title} className={`inline-flex items-center gap-1 whitespace-nowrap rounded-full px-2 py-0.5 text-xs font-medium ${tones[tone]}`}>
      {children}
    </span>
  );
}

const SEVERITY_TONE: Record<Severity, Tone> = { critical: "danger", high: "orange", medium: "warn", low: "ok" };

export function SeverityBadge({ severity }: { severity: Severity }) {
  return <Badge tone={SEVERITY_TONE[severity] ?? "neutral"}>{severity.charAt(0).toUpperCase() + severity.slice(1)}</Badge>;
}

const STATUS_TONE: Record<Status, Tone> = { open: "danger", investigating: "warn", resolved: "ok", ignored: "neutral" };
export const STATUS_LABEL: Record<Status, string> = { open: "Open", investigating: "Investigating", resolved: "Resolved", ignored: "Ignored" };

export function StatusBadge({ status }: { status: Status }) {
  return <Badge tone={STATUS_TONE[status] ?? "neutral"}>{STATUS_LABEL[status] ?? status}</Badge>;
}

export function levelTone(level: string): Tone {
  return level === "CRITICAL" || level === "ERROR" ? "danger" : level === "WARNING" ? "warn" : "neutral";
}

export function LevelBadge({ level }: { level: string }) {
  return <Badge tone={levelTone(level)}>{level}</Badge>;
}

/** Where a statement came from. Colour AND icon AND words, so it never relies on colour alone. */
const ORIGIN: Record<string, { label: string; hint: string; cls: string; icon: typeof Eye }> = {
  observed: { label: "Observed", hint: "Read directly from log records", cls: "bg-origin-observed-bg text-origin-observed", icon: Eye },
  inferred: { label: "Inferred", hint: "Concluded from the records; not confirmed", cls: "bg-origin-observed-bg text-origin-observed", icon: Eye },
  runbook: { label: "Runbook", hint: "Quoted from a retrieved runbook section", cls: "bg-origin-runbook-bg text-origin-runbook", icon: BookOpen },
  rule: { label: "Rule", hint: "Drawn by a fixed rule in this application; not proof", cls: "bg-origin-rule-bg text-origin-rule", icon: Ruler },
  ai_hypothesis: { label: "AI hypothesis", hint: "Written by an AI model; it may be wrong", cls: "bg-origin-ai-bg text-origin-ai", icon: Bot },
};

export function OriginBadge({ origin }: { origin: Origin | string }) {
  const info = ORIGIN[origin] ?? { label: origin, hint: "", cls: "bg-slate-100 text-ink", icon: Lightbulb };
  const Icon = info.icon;
  return (
    <span title={info.hint} className={`inline-flex items-center gap-1 whitespace-nowrap rounded-full px-2 py-0.5 text-xs font-medium ${info.cls}`}>
      <Icon className="h-3 w-3" aria-hidden />
      {info.label}
    </span>
  );
}

const STRENGTH_TONE: Record<Strength, Tone> = { strong: "ok", moderate: "info", weak: "neutral" };

export function StrengthBadge({ strength, reason }: { strength: Strength; reason?: string }) {
  return (
    <Badge tone={STRENGTH_TONE[strength] ?? "neutral"} title={reason}>
      {strength.charAt(0).toUpperCase() + strength.slice(1)} support
    </Badge>
  );
}
