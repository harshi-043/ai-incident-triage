import { Trash2 } from "lucide-react";
import { api } from "../api/endpoints";
import { errorMessage } from "../api/client";
import { useState } from "react";
import { useApp } from "../context/AppContext";
import { useAsync } from "../hooks/useAsync";
import { ConfirmButton } from "../components/ConfirmButton";
import { Badge } from "../components/ui/Badge";
import { Card, CardHeader, PageHeader } from "../components/ui/Card";
import { ErrorState, LoadingState, Note } from "../components/ui/States";
import { formatBytes, formatNumber, formatTime } from "../lib/format";

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-wrap justify-between gap-x-4 gap-y-0.5 border-b border-line py-2 text-sm last:border-0">
      <dt className="text-muted">{label}</dt>
      <dd className="min-w-0 break-words text-right text-ink">{children}</dd>
    </div>
  );
}

export function SettingsPage() {
  const settings = useAsync((signal) => api.settings(signal), []);
  const health = useAsync((signal) => api.health(signal), []);
  const { sources, refresh } = useApp();
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  async function removeSource(id: string) {
    setBusy(id);
    setError(null);
    try {
      await api.deleteSource(id);
      await refresh();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(null);
    }
  }

  const s = settings.data;
  return (
    <>
      <PageHeader title="Settings" description="What the server is set to use. These are read-only here: they come from environment variables, so no key is ever typed into or stored by the browser." />
      {settings.loading && !s ? <LoadingState /> : settings.error ? <ErrorState message={settings.error} onRetry={settings.reload} /> : s && (
        <div className="grid gap-5 lg:grid-cols-2">
          <Card>
            <CardHeader title="AI provider" subtitle="Optional. The tool works without it." />
            <dl>
              <Row label="Provider">{s.ai.provider}</Row>
              <Row label="Model">{s.ai.model ?? "not set"}</Row>
              <Row label="API key">{s.ai.key_set ? <Badge tone="ok">set (hidden)</Badge> : <Badge tone="neutral">not set</Badge>}</Row>
              <Row label="Ready to use">{s.ai.ready ? <Badge tone="ok">yes</Badge> : <Badge tone="neutral">no</Badge>}</Row>
              <Row label="Request timeout">{s.ai.timeout_seconds} s</Row>
              <Row label="Max records sent">{s.ai.max_evidence_records}</Row>
            </dl>
            {s.ai.problem && <div className="mt-3"><Note>{s.ai.problem}</Note></div>}
            <p className="mt-3 text-xs text-muted">{s.how_to_change}</p>
          </Card>

          <Card>
            <CardHeader title="Search (retrieval)" />
            <dl>
              <Row label="Method">{s.retrieval.embedding_backend}</Row>
              <Row label="Embedding model">{s.retrieval.embedding_model}</Row>
              <Row label="Section size">{s.retrieval.chunk_size_chars} characters</Row>
              <Row label="Overlap">{s.retrieval.chunk_overlap_chars} characters</Row>
              <Row label="Minimum match">{s.retrieval.min_relevance}</Row>
            </dl>
          </Card>

          <Card>
            <CardHeader title="Incident detection defaults" />
            <dl>
              <Row label="Similarity threshold">{s.detection_defaults.similarity_threshold}</Row>
              <Row label="Gap between bursts">{s.detection_defaults.gap_minutes} min</Row>
              <Row label="Minimum errors">{s.detection_defaults.min_errors}</Row>
            </dl>
            <p className="mt-3 text-xs text-muted">You can change these per run on the Dashboard.</p>
          </Card>

          <Card>
            <CardHeader title="Limits" />
            <dl>
              <Row label="Log upload">{s.limits.max_upload_mb} MB</Row>
              <Row label="Records per log">{formatNumber(s.limits.max_log_records)}</Row>
              <Row label="Runbook upload">{s.limits.max_runbook_mb} MB</Row>
            </dl>
          </Card>

          <Card className="lg:col-span-2">
            <CardHeader title="Privacy and safety" />
            <p className="text-sm text-ink">{s.safety}</p>
            <p className="mt-2 text-sm text-ink">{s.privacy}</p>
          </Card>
        </div>
      )}

      <div className="mt-5 grid gap-5 lg:grid-cols-2">
        <Card>
          <CardHeader title="Server health" />
          {health.loading && !health.data ? <LoadingState /> : health.error ? <ErrorState message={health.error} onRetry={health.reload} /> : health.data && (
            <dl>
              <Row label="Status">{health.data.status}</Row>
              <Row label="Version">{health.data.version}</Row>
              {Object.entries(health.data.checks).map(([k, v]) => <Row key={k} label={k}>{v}</Row>)}
            </dl>
          )}
        </Card>

        <Card>
          <CardHeader title="Loaded log sources" subtitle="Deleting a source also deletes its analyses, incidents, notes and summaries." />
          {error && <Note tone="danger">{error}</Note>}
          {sources.length === 0 ? <p className="text-sm text-muted">No log sources are loaded.</p> : (
            <ul className="divide-y divide-line">
              {sources.map((src) => (
                <li key={src.id} className="flex flex-wrap items-center justify-between gap-2 py-2.5">
                  <div className="min-w-0">
                    <p className="break-words text-sm font-medium text-ink">{src.name}</p>
                    <p className="text-xs text-muted">{formatNumber(src.record_count)} records · {formatBytes(src.size_bytes)} · {src.kind === "sample" ? "sample (synthetic)" : "uploaded"} · {formatTime(src.created_at, false)} UTC</p>
                  </div>
                  <ConfirmButton label={`Delete ${src.name}`} icon={<Trash2 className="h-4 w-4" aria-hidden />} busy={busy === src.id} onConfirm={() => removeSource(src.id)} />
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
    </>
  );
}
