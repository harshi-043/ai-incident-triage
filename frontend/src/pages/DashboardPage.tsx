import { useNavigate } from "react-router-dom";
import { api } from "../api/endpoints";
import { useApp } from "../context/AppContext";
import { useAsync } from "../hooks/useAsync";
import { formatNumber, formatTime, plural } from "../lib/format";
import type { Incident, Level } from "../api/types";
import { AnalyzePanel } from "../components/AnalysisGate";
import { LoadLogsPanel } from "../components/LoadLogsPanel";
import { COLORS, ChartFrame } from "../components/charts/ChartFrame";
import { HorizontalBars, TrendChart } from "../components/charts/Charts";
import { SeverityBadge, StatusBadge } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";
import { Card, CardHeader, PageHeader, StatCard } from "../components/ui/Card";
import { EmptyState, ErrorState, LoadingState, Note } from "../components/ui/States";

const LEVEL_COLOR: Record<Level, string> = {
  DEBUG: "#b4c0c7", INFO: "#7d8c96", WARNING: COLORS.warning, ERROR: COLORS.error, CRITICAL: "#7f2621",
};

export function DashboardPage() {
  const { selected, analysis, loading: appLoading, error: appError, refresh } = useApp();
  const navigate = useNavigate();
  const { data, error, loading, reload } = useAsync(
    (signal) => api.dashboard(selected?.id, signal),
    [selected?.id, analysis?.id],
    !appLoading && !!selected,
  );

  if (appError) return <ErrorState message={appError} onRetry={() => void refresh()} />;
  if (appLoading) return <LoadingState label="Loading..." />;

  if (!selected) {
    return (
      <>
        <PageHeader title="Dashboard" description="Group related errors, find incidents, look up runbooks and get read-only checks that link back to the log evidence." />
        <EmptyState title="Start by loading some logs" action={<LoadLogsPanel />}>
          Upload your own file, or load a built-in sample. The samples are synthetic: invented web-shop and routing logs with known injected problems.
        </EmptyState>
      </>
    );
  }
  if (loading) return <LoadingState label="Loading dashboard..." />;
  if (error || !data) return <ErrorState message={error ?? "The dashboard could not be loaded."} onRetry={reload} />;
  if (!data.has_data || !data.totals) return <EmptyState title="No data">{data.reason}</EmptyState>;

  const totals = data.totals;
  const inc = data.incidents;
  const errorRate = totals.records ? totals.errors / totals.records : 0;
  const levels = (data.severity_distribution ?? []).filter((d) => d.count > 0);

  return (
    <>
      <PageHeader
        title="Dashboard"
        description={
          <>
            {selected.name} · {plural(totals.records, "record")}
            {selected.kind === "sample" && " · synthetic sample data"}
          </>
        }
        action={<Button variant="secondary" onClick={() => navigate("/logs")}>Open Log Explorer</Button>}
      />

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatCard label="Log records" value={formatNumber(totals.records)} hint={`${formatNumber(totals.info)} informational`} />
        <StatCard label="Error-level records" value={formatNumber(totals.errors)} tone={totals.errors ? "danger" : "default"} hint={`${(errorRate * 100).toFixed(1)}% of all records`} />
        <StatCard label="Warnings" value={formatNumber(totals.warnings)} tone={totals.warnings ? "warn" : "default"} />
        <StatCard
          label="Incidents"
          value={inc && !data.analysis_needed ? formatNumber(inc.total) : "—"}
          tone={inc && inc.critical_or_high ? "danger" : "default"}
          hint={data.analysis_needed ? "Not analysed yet" : `${formatNumber(inc?.critical_or_high ?? 0)} critical or high`}
        />
      </div>

      <div className="mt-5 grid gap-5 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <ChartFrame
            title="Errors and warnings over time"
            subtitle="Times are UTC, as written in the log."
            summary={`${formatNumber(totals.errors)} error-level records and ${formatNumber(totals.warnings)} warnings.`}
          >
            {data.trend && data.trend.points.length > 0 ? (
              <TrendChart data={data.trend.points} bucketSeconds={data.trend.bucket_seconds} />
            ) : (
              <p className="p-6 text-sm text-muted">These records have no usable timestamps, so there is no time chart.</p>
            )}
          </ChartFrame>
        </div>
        <ChartFrame title="Records by level" summary={levels.map((l) => `${l.level} ${l.count}`).join(", ")}>
          <HorizontalBars data={levels.map((l) => ({ name: l.level, value: l.count, color: LEVEL_COLOR[l.level] }))} valueLabel="Records" labelWidth={84} />
        </ChartFrame>
      </div>

      {data.analysis_needed ? (
        <div className="mt-5 space-y-3">
          <Note>This log has not been analysed yet. Analysing groups the errors and looks for incidents.</Note>
          <AnalyzePanel />
        </div>
      ) : (
        <div className="mt-5 grid gap-5 lg:grid-cols-2">
          <Card>
            <CardHeader
              title="Recent incidents"
              subtitle={inc ? `${plural(inc.total, "incident")} found. Open one to see its timeline and evidence.` : undefined}
              action={<Button variant="ghost" onClick={() => navigate("/incidents")}>See all</Button>}
            />
            {inc && inc.recent.length > 0 ? (
              <ul className="divide-y divide-line">
                {inc.recent.map((i: Incident) => (
                  <li key={i.id}>
                    <button type="button" onClick={() => navigate(`/incidents/${i.id}`)} className="flex w-full flex-col gap-1 rounded px-1 py-2.5 text-left hover:bg-ocean-50">
                      <span className="flex flex-wrap items-center gap-2">
                        <span className="font-mono text-xs text-muted">{i.label}</span>
                        <SeverityBadge severity={i.severity} />
                        <StatusBadge status={i.status} />
                      </span>
                      <span className="line-clamp-2 break-words text-sm font-medium text-ink">{i.title}</span>
                      <span className="text-xs text-muted">{formatTime(i.first_seen, false)} · {plural(i.error_count, "error")} · {i.services.join(", ")}</span>
                    </button>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-muted">No incidents were found with the current settings. Lower "Errors needed for an incident" on the analysis settings to look for smaller bursts.</p>
            )}
          </Card>

          <ChartFrame
            title="Services with the most errors"
            summary={(data.top_services ?? []).map((s) => `${s.service} ${s.errors}`).join(", ")}
            height={Math.max(180, (data.top_services?.length ?? 1) * 34 + 40)}
          >
            <HorizontalBars data={(data.top_services ?? []).map((s) => ({ name: s.service, value: s.errors }))} valueLabel="Error-level records" labelWidth={130} color={COLORS.error} />
          </ChartFrame>

          <Card>
            <CardHeader title="Most frequent error patterns" subtitle="Messages with ids and numbers masked, so similar errors count together." />
            <ul className="space-y-2">
              {(data.top_errors ?? []).slice(0, 6).map((g) => (
                <li key={g.id} className="flex items-start justify-between gap-3 text-sm">
                  <span className="min-w-0 break-words text-ink">{g.title}</span>
                  <span className="shrink-0 tabular-nums font-medium text-muted">{formatNumber(g.record_count)}</span>
                </li>
              ))}
            </ul>
          </Card>

          <Card>
            <CardHeader title="Recent activity" subtitle="Status changes, notes and summaries." />
            {data.recent_activity && data.recent_activity.length > 0 ? (
              <ul className="space-y-2 text-sm">
                {data.recent_activity.map((a, idx) => (
                  <li key={`${a.created_at}-${idx}`} className="flex items-start justify-between gap-3">
                    <span className="min-w-0 break-words">{a.detail}</span>
                    <time className="shrink-0 text-xs text-muted" dateTime={a.created_at}>{formatTime(a.created_at, false)}</time>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-muted">Nothing yet. Change an incident's status or add a note and it will appear here.</p>
            )}
          </Card>
        </div>
      )}
    </>
  );
}
