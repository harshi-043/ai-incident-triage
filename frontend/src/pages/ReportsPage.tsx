import { Link } from "react-router-dom";
import { api } from "../api/endpoints";
import { useApp } from "../context/AppContext";
import { useAsync } from "../hooks/useAsync";
import { AnalysisGate } from "../components/AnalysisGate";
import { ExportButtons } from "../components/ExportButtons";
import { SeverityBadge, StatusBadge } from "../components/ui/Badge";
import { Card, CardHeader, PageHeader } from "../components/ui/Card";
import { EmptyState, ErrorState, LoadingState, Note } from "../components/ui/States";
import { formatNumber, formatTime } from "../lib/format";

export function ReportsPage() {
  return (
    <>
      <PageHeader title="Reports" description="Download a report of the incidents found in the selected log, or one incident at a time. Reports list facts, runbook text and hypotheses in separate sections." />
      <AnalysisGate>
        <Reports />
      </AnalysisGate>
    </>
  );
}

function Reports() {
  const { selected, analysis } = useApp();
  const incidents = useAsync((signal) => api.incidents({ analysis_id: analysis!.id, sort: "number", order: "asc", page_size: 200 }, signal), [analysis?.id]);
  const history = useAsync((signal) => api.analyses(selected!.id, signal), [selected?.id]);

  return (
    <div className="space-y-5">
      <Card>
        <CardHeader title="Full report" subtitle={`${selected!.name}: ${formatNumber(selected!.record_count)} records, ${formatNumber(analysis!.stats.incident_count)} incident(s), ${formatNumber(analysis!.stats.group_count)} error pattern(s).`} />
        <ExportButtons kind="report" id={selected!.id} />
        <p className="mt-3 text-xs text-muted">Markdown is for reading, JSON for other programs, CSV for spreadsheets. Text copied from logs is cleaned so a spreadsheet cannot run it as a formula.</p>
      </Card>

      <Card>
        <CardHeader title="One incident" />
        {incidents.loading && !incidents.data ? <LoadingState /> : incidents.error ? <ErrorState message={incidents.error} onRetry={incidents.reload} /> : (incidents.data?.items.length ?? 0) === 0 ? (
          <EmptyState title="No incidents to export">This analysis found no incidents.</EmptyState>
        ) : (
          <ul className="divide-y divide-line">
            {incidents.data!.items.map((i) => (
              <li key={i.id} className="flex flex-wrap items-center justify-between gap-3 py-2.5">
                <div className="min-w-0">
                  <p className="flex flex-wrap items-center gap-2 text-sm">
                    <Link to={`/incidents/${i.id}`} className="font-medium text-ocean-700 underline">{i.label}</Link>
                    <SeverityBadge severity={i.severity} />
                    <StatusBadge status={i.status} />
                  </p>
                  <p className="break-words text-xs text-muted">{i.title}</p>
                </div>
                <ExportButtons kind="incident" id={i.id} />
              </li>
            ))}
          </ul>
        )}
      </Card>

      <Card>
        <CardHeader title="Analysis history" subtitle="Each run with different settings is kept, so earlier results are not lost." />
        {history.loading && !history.data ? <LoadingState /> : history.error ? <ErrorState message={history.error} onRetry={history.reload} /> : (
          <ul className="space-y-1.5 text-sm">
            {history.data!.items.map((a) => (
              <li key={a.id} className={a.id === analysis!.id ? "font-medium text-ink" : "text-muted"}>
                {formatTime(a.created_at, false)} UTC: {a.stats.incident_count} incident(s), {a.stats.group_count} pattern(s); similarity {a.params.similarity_threshold}, gap {a.params.gap_minutes} min, min errors {a.params.min_errors}
                {a.id === analysis!.id && " (current)"}
              </li>
            ))}
          </ul>
        )}
        <div className="mt-3"><Note>Reports describe what the tool found. They are not a confirmed root cause.</Note></div>
      </Card>
    </div>
  );
}
