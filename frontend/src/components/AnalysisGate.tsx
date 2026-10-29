import { useState, type ReactNode } from "react";
import { Play } from "lucide-react";
import { errorMessage } from "../api/client";
import { useApp } from "../context/AppContext";
import { formatNumber } from "../lib/format";
import { LoadLogsPanel } from "./LoadLogsPanel";
import { Button } from "./ui/Button";
import { Card, CardHeader } from "./ui/Card";
import { NumberField, ToggleField } from "./ui/Fields";
import { EmptyState, ErrorState, LoadingState, Note } from "./ui/States";

/** Controls for the grouping and incident rules. Used on the dashboard gate and in re-run dialogs. */
export function AnalyzePanel({ title = "Find incidents in this log" }: { title?: string }) {
  const { selected, analysis, runAnalysis } = useApp();
  const [similarity, setSimilarity] = useState(0.6);
  const [gap, setGap] = useState(10);
  const [minErrors, setMinErrors] = useState(5);
  const [merge, setMerge] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);

  const valid = similarity >= 0.1 && similarity <= 0.99 && gap >= 1 && gap <= 240 && minErrors >= 2 && minErrors <= 10000;

  async function run(forceNew: boolean) {
    setBusy(true);
    setError(null);
    setNote(null);
    try {
      const res = await runAnalysis({ similarity_threshold: similarity, gap_minutes: gap, min_errors: minErrors, merge_across_services: merge, force_new: forceNew });
      setNote(`${formatNumber(res.stats.incident_count)} incident(s) found in ${formatNumber(res.stats.group_count)} error pattern(s).`);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardHeader
        title={title}
        subtitle={`Errors are grouped by wording, then bursts of errors in time become incidents. Source: ${selected?.name ?? "none selected"}.`}
      />
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <NumberField label="Wording similarity" value={similarity} onChange={setSimilarity} min={0.1} max={0.99} step={0.05} hint="Higher keeps patterns separate." />
        <NumberField label="Gap that ends an incident (min)" value={gap} onChange={setGap} min={1} max={240} />
        <NumberField label="Errors needed for an incident" value={minErrors} onChange={setMinErrors} min={2} max={10000} />
        <div className="self-end pb-1">
          <ToggleField label="Merge across services" checked={merge} onChange={setMerge} hint="Off keeps each service separate." />
        </div>
      </div>
      <div className="mt-4 flex flex-wrap items-center gap-2">
        <Button busy={busy} disabled={!valid || !selected} onClick={() => void run(false)} icon={<Play className="h-4 w-4" aria-hidden />}>
          {analysis ? "Run again with these settings" : "Find incidents"}
        </Button>
        {analysis && (
          <Button variant="secondary" busy={busy} disabled={!valid} onClick={() => void run(true)}>
            Force a new analysis
          </Button>
        )}
      </div>
      <div className="mt-3 space-y-2" aria-live="polite">
        {note && <Note>{note}</Note>}
        {error && <p role="alert" className="text-sm text-danger">{error}</p>}
      </div>
    </Card>
  );
}

/**
 * Wraps a page that needs a log source (and, with `needsAnalysis`, a finished analysis).
 * It says what is missing instead of showing an empty page.
 */
export function AnalysisGate({ needsAnalysis = true, children }: { needsAnalysis?: boolean; children: ReactNode }) {
  const { selected, analysis, loading, error, refresh } = useApp();
  if (error) return <ErrorState message={error} onRetry={() => void refresh()} />;
  if (loading) return <LoadingState label="Loading log sources..." />;
  if (!selected) {
    return (
      <EmptyState title="No log data yet" action={<LoadLogsPanel />}>
        Upload a log file, or load a synthetic sample to see how the tool works. Every page works on the log source you select.
      </EmptyState>
    );
  }
  if (needsAnalysis && !analysis) {
    return (
      <div className="space-y-4">
        <Note>{selected.name} is loaded but has not been analysed yet. Run the analysis to find incidents.</Note>
        <AnalyzePanel />
      </div>
    );
  }
  return <>{children}</>;
}
