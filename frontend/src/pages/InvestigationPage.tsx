import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Sparkles } from "lucide-react";
import { api } from "../api/endpoints";
import { errorMessage } from "../api/client";
import { useApp } from "../context/AppContext";
import { useAsync } from "../hooks/useAsync";
import type { Summary } from "../api/types";
import { AnalysisGate } from "../components/AnalysisGate";
import { AskPanel } from "../components/AskPanel";
import { ExportButtons } from "../components/ExportButtons";
import { SummaryView } from "../components/SummaryView";
import { Button } from "../components/ui/Button";
import { Card, PageHeader } from "../components/ui/Card";
import { SelectField, ToggleField } from "../components/ui/Fields";
import { EmptyState, ErrorState, LoadingState, Note } from "../components/ui/States";

export function InvestigationPage() {
  return (
    <>
      <PageHeader
        title="AI Investigation"
        description="A structured summary of one incident: facts from the logs, matching runbook text, hypotheses and read-only checks. It works without any AI service."
      />
      <AnalysisGate>
        <Investigation />
      </AnalysisGate>
    </>
  );
}

function Investigation() {
  const { analysis } = useApp();
  const [params, setParams] = useSearchParams();
  const list = useAsync((signal) => api.incidents({ analysis_id: analysis!.id, sort: "number", order: "asc", page_size: 200 }, signal), [analysis?.id]);
  const settings = useAsync((signal) => api.settings(signal), []);

  const incidents = list.data?.items ?? [];
  const requested = params.get("incident");
  const incidentId = incidents.find((i) => i.id === requested)?.id ?? incidents[0]?.id ?? "";

  const [useAi, setUseAi] = useState(false);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Show the last saved summary of the chosen incident, if any.
  const saved = useAsync((signal) => api.summary(incidentId, signal), [incidentId], !!incidentId);
  useEffect(() => {
    setSummary(saved.data?.summary ?? null);
    setError(null);
  }, [saved.data, incidentId]);

  if (list.loading && !list.data) return <LoadingState label="Loading incidents..." />;
  if (list.error) return <ErrorState message={list.error} onRetry={list.reload} />;
  if (incidents.length === 0) {
    return <EmptyState title="No incidents to investigate">The analysis did not find any incidents. Change the analysis settings on the Dashboard to look for smaller bursts of errors.</EmptyState>;
  }

  const ai = settings.data?.ai;
  const aiReady = !!ai?.ready;

  async function generate() {
    setBusy(true);
    setError(null);
    try {
      setSummary((await api.summarize(incidentId, useAi && aiReady)).summary);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-5">
      <Card>
        <div className="grid gap-4 md:grid-cols-2">
          <SelectField
            label="Incident"
            value={incidentId}
            onChange={(value) => setParams({ incident: value })}
            options={incidents.map((i) => ({ value: i.id, label: `${i.label} · ${i.severity} · ${i.title.slice(0, 70)}` }))}
          />
          <div>
            <ToggleField
              label={ai?.ready ? `Also ask the AI provider (${ai.provider}${ai.model ? `: ${ai.model}` : ""})` : "Also ask an AI provider"}
              checked={useAi && aiReady}
              onChange={setUseAi}
              hint={
                aiReady
                  ? `Sends up to ${ai?.max_evidence_records} log records of this incident, clipped, with emails, IP addresses and tokens hidden, plus runbook excerpts, to that provider. Off by default.`
                  : "Not available: no AI provider is configured. The summary works without one."
              }
            />
            {!aiReady && (
              <p className="mt-1 pl-6 text-xs text-muted">{ai?.problem ?? "To turn it on, set AI_PROVIDER, AI_MODEL and AI_API_KEY (see the README) and restart the server."}</p>
            )}
          </div>
        </div>
        <div className="mt-4 flex flex-wrap items-center gap-3">
          <Button busy={busy} onClick={() => void generate()} icon={<Sparkles className="h-4 w-4" aria-hidden />}>
            {summary ? "Generate again" : "Generate summary"}
          </Button>
          {summary && <ExportButtons kind="incident" id={incidentId} />}
        </div>
        {error && <p role="alert" className="mt-3 text-sm text-danger">{error}</p>}
      </Card>

      {saved.loading && !summary && <LoadingState label="Checking for a saved summary..." />}
      {!summary && !saved.loading && !busy && <Note>No summary has been generated for this incident yet. Click "Generate summary".</Note>}
      {summary && <SummaryView summary={summary} />}
      {incidentId && <AskPanel incidentId={incidentId} useAi={useAi && aiReady} />}
    </div>
  );
}
