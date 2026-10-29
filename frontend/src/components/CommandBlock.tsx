import { Terminal } from "lucide-react";

/** Commands that a runbook documents. They are shown as text for a person to read; there is no way to run them here. */
export function CommandBlock({ commands }: { commands: string[] }) {
  if (commands.length === 0) return null;
  return (
    <div className="mt-2 rounded-lg border border-line bg-slate-100">
      <p className="flex items-center gap-1.5 border-b border-line px-3 py-1.5 text-xs font-medium text-muted">
        <Terminal className="h-3.5 w-3.5" aria-hidden />
        Documented in the runbook. For a person to review. This application does not run commands.
      </p>
      <pre className="overflow-x-auto whitespace-pre-wrap break-words p-3 font-mono text-xs text-ink">{commands.join("\n")}</pre>
    </div>
  );
}
