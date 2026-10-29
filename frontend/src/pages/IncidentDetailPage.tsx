import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ArrowLeft, Microscope, Plus, Trash2 } from "lucide-react";
import { api } from "../api/endpoints";
import { errorMessage } from "../api/client";
import { useAsync } from "../hooks/useAsync";
import { formatDuration, formatNumber, formatTime } from "../lib/format";
import type { IncidentDetail, Status } from "../api/types";
import { ConfirmButton } from "../components/ConfirmButton";
import { EvidenceChips } from "../components/EvidenceChips";
import { ExportButtons } from "../components/ExportButtons";
import { RunbookHitCard } from "../components/RunbookHitCard";
import { Timeline } from "../components/Timeline";
import { useRecordViewer } from "../components/RecordViewer";
import { Badge, LevelBadge, OriginBadge, SeverityBadge, STATUS_LABEL } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";
import { Card, CardHeader } from "../components/ui/Card";
import { DataTable, type Column } from "../components/ui/DataTable";
import { ChipGroup, SelectField } from "../components/ui/Fields";
import { Pagination } from "../components/ui/Pagination";
import { ErrorState, LoadingState, Note } from "../components/ui/States";
import type { LogRecord } from "../api/types";

export function IncidentDetailPage() {
  const { id = "" } = useParams();
  const { data, error, loading, reload } = useAsync((signal) => api.incident(id, signal), [id]);

  if (loading && !data) return <LoadingState label="Loading incident..." />;
  if (error || !data) {
    return (
      <div className="space-y-3">
        <BackLink />
        <ErrorState message={error ?? "The incident could not be loaded."} onRetry={reload} />
      </div>
    );
  }
  return <Detail data={data} reload={reload} />;
}

function BackLink() {
  return (
    <Link to="/incidents" className="inline-flex items-center gap-1 text-sm font-medium text-ocean-700 hover:underline">
      <ArrowLeft className="h-4 w-4" aria-hidden /> All incidents
    </Link>
  );
}

function Detail({ data, reload }: { data: IncidentDetail; reload: () => void }) {
  const { incident } = data;
  const navigate = useNavigate();
  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState<string | null>(null);
  const [saveErr, setSaveErr] = useState<string | null>(null);

  async function update(body: { status?: string; reviewed?: boolean }) {
    setSaving(true);
    setSaveErr(null);
    setSaveMsg(null);
    try {
      await api.updateIncident(incident.id, body);
      setSaveMsg("Saved.");
      reload();
    } catch (err) {
      setSaveErr(errorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="space-y-5">
      <BackLink />
      <header className="space-y-3">
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-mono text-sm text-muted">{incident.label}</span>
          <SeverityBadge severity={incident.severity} />
          {data.source?.kind === "sample" && <Badge tone="info">Synthetic sample</Badge>}
        </div>
        <h1 className="break-words text-xl font-semibold tracking-tight text-ink sm:text-2xl">{incident.title}</h1>
        <p className="text-sm text-muted">
          {formatTime(incident.first_seen)} to {formatTime(incident.last_seen)} UTC · lasted {formatDuration(incident.first_seen, incident.last_seen)} ·{" "}
          {formatNumber(incident.error_count)} error-level records · {incident.services.join(", ")}
        </p>
        <div className="flex flex-wrap items-end gap-4">
          <div className="w-48">
            <SelectField
              label="Status"
              value={incident.status}
              disabled={saving}
              onChange={(value) => void update({ status: value as Status })}
              options={Object.entries(STATUS_LABEL).map(([value, label]) => ({ value, label }))}
            />
          </div>
          <label className="flex items-center gap-2 pb-2 text-sm">
            <input type="checkbox" className="h-4 w-4 accent-ocean-700" checked={incident.reviewed} disabled={saving} onChange={(e) => void update({ reviewed: e.target.checked })} />
            Marked as reviewed
          </label>
          <div className="pb-1" aria-live="polite">
            {saveMsg && <span className="text-sm text-ok">{saveMsg}</span>}
            {saveErr && <span role="alert" className="text-sm text-danger">{saveErr}</span>}
          </div>
          <div className="ml-auto flex flex-wrap items-end gap-3">
            <Button icon={<Microscope className="h-4 w-4" aria-hidden />} onClick={() => navigate(`/investigation?incident=${incident.id}`)}>
              Open AI investigation
            </Button>
            <ExportButtons kind="incident" id={incident.id} />
          </div>
        </div>
      </header>

      <Card>
        <CardHeader title="Why this was flagged" subtitle="The rule that created this incident, in plain words." />
        <p className="text-sm text-ink">{data.explanation}</p>
        <dl className="mt-3 grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
          {[
            ["Busiest window errors", data.detection.peak_window_errors],
            ["Warnings attached", data.detection.attached_warning_records],
            ["Context events", data.detection.context_events],
            ["Gap that ends an incident", data.detection.gap_minutes !== undefined ? `${data.detection.gap_minutes} min` : null],
          ].map(([label, value]) => (
            <div key={label as string}>
              <dt className="text-xs text-muted">{label as string}</dt>
              <dd className="font-semibold tabular-nums">{value === null || value === undefined ? "—" : String(value)}</dd>
            </div>
          ))}
        </dl>
      </Card>

      <Card>
        <CardHeader
          title="Timeline"
          subtitle={<>Each event shows where it came from: <OriginBadge origin="observed" /> read from the records, or <OriginBadge origin="inferred" /> concluded from them. Click a record number to open it.</>}
        />
        <Timeline events={data.timeline} />
      </Card>

      <Card>
        <CardHeader title="Error patterns" subtitle="Records grouped by service, exception type and wording once ids and numbers are masked. Similar wording is not proof of a shared cause." />
        <ul className="divide-y divide-line">
          {data.groups.map((g) => (
            <li key={g.id} className="py-3 first:pt-0 last:pb-0">
              <p className="break-words text-sm font-medium text-ink">{g.title}</p>
              <p className="mt-0.5 text-xs text-muted">
                {formatNumber(g.record_count)} records · {g.services.join(", ")} · grouped by {g.method === "exact" ? "identical wording" : "similar wording"}
              </p>
              <p className="mt-1 text-sm text-muted">{g.explanation}</p>
              <div className="mt-1"><EvidenceChips ids={g.sample_record_ids} label="Examples" /></div>
            </li>
          ))}
        </ul>
      </Card>

      <RunbookSection incidentId={incident.id} />
      <EvidenceTable incidentId={incident.id} />

      {data.related_incidents.length > 0 && (
        <Card>
          <CardHeader title="Related incidents" subtitle="They share at least one error pattern. They may or may not have the same cause." />
          <ul className="space-y-2 text-sm">
            {data.related_incidents.map((r) => (
              <li key={r.id} className="flex flex-wrap items-center gap-2">
                <Link to={`/incidents/${r.id}`} className="font-medium text-ocean-700 hover:underline">{r.label}</Link>
                <SeverityBadge severity={r.severity} />
                <span className="break-words text-muted">{r.title}</span>
              </li>
            ))}
          </ul>
        </Card>
      )}

      <Notes incidentId={incident.id} notes={data.notes} reload={reload} />
    </div>
  );
}

function RunbookSection({ incidentId }: { incidentId: string }) {
  const { data, error, loading, reload } = useAsync((signal) => api.incidentRunbooks(incidentId, signal), [incidentId]);
  return (
    <Card>
      <CardHeader title="Matching runbook sections" subtitle="Retrieved from the knowledge base. This is quoted documentation, not an instruction to run anything." />
      {loading && <LoadingState label="Looking up runbooks..." />}
      {error && <ErrorState message={error} onRetry={reload} />}
      {data && data.no_relevant_source && <Note tone="warn">{data.message}</Note>}
      {data && !data.no_relevant_source && (
        <div className="space-y-3">
          {data.retrieval.fallback && <Note tone="warn">The requested search model was not available, so a simpler keyword search was used. ({data.retrieval.fallback_reason})</Note>}
          {data.results.map((hit) => (
            <RunbookHitCard key={hit.chunk_id} citation={hit.citation} relevance={hit.relevance} text={hit.text} commands={hit.documented_commands} />
          ))}
        </div>
      )}
    </Card>
  );
}

const LEVEL_OPTIONS = ["CRITICAL", "ERROR", "WARNING", "INFO"].map((l) => ({ value: l, label: l }));

function EvidenceTable({ incidentId }: { incidentId: string }) {
  const viewer = useRecordViewer();
  const [levels, setLevels] = useState<string[]>(["CRITICAL", "ERROR"]);
  const [page, setPage] = useState(1);
  const { data, error, loading, reload } = useAsync(
    (signal) => api.incidentRecords(incidentId, { level: levels, page, page_size: 20 }, signal),
    [incidentId, levels, page],
  );
  const columns: Column<LogRecord>[] = [
    { key: "id", label: "Record", render: (r) => <span className="font-mono text-xs text-ocean-700">#{r.id}</span> },
    { key: "timestamp", label: "Time (UTC)", render: (r) => <span className="font-mono text-xs">{formatTime(r.timestamp)}</span> },
    { key: "level", label: "Level", render: (r) => <LevelBadge level={r.level} /> },
    { key: "service", label: "Service" },
    { key: "message", label: "Message", render: (r) => <span className="block max-w-xl truncate font-mono text-xs" title={r.message}>{r.message}</span> },
  ];
  return (
    <Card>
      <CardHeader title="Evidence records" subtitle="Every record that belongs to this incident. Click a row for the full text and the lines around it." />
      <div className="mb-3"><ChipGroup label="Show levels" selected={levels} onChange={(v) => { setLevels(v); setPage(1); }} options={LEVEL_OPTIONS} /></div>
      {error && <ErrorState message={error} onRetry={reload} />}
      {loading && !data && <LoadingState label="Loading records..." />}
      {data && (
        <div className={loading ? "opacity-60" : ""}>
          <DataTable caption="Incident records" columns={columns} rows={data.items} rowKey={(r) => String(r.id)} onRowClick={(r) => viewer.open(r.id)} emptyText="No records at these levels." />
          <Pagination page={page} totalPages={Math.max(1, Math.ceil(data.total / 20))} total={data.total} pageSize={20} onPage={setPage} noun="records" />
        </div>
      )}
    </Card>
  );
}

function Notes({ incidentId, notes, reload }: { incidentId: string; notes: IncidentDetail["notes"]; reload: () => void }) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function add() {
    setBusy(true);
    setError(null);
    try {
      await api.addNote(incidentId, text);
      setText("");
      reload();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }
  async function remove(noteId: number) {
    try {
      await api.deleteNote(incidentId, noteId);
      reload();
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  return (
    <Card>
      <CardHeader title="Notes" subtitle="Your own notes on this incident. They are saved in the local database." />
      <label htmlFor="note-text" className="sr-only">New note</label>
      <textarea
        id="note-text"
        value={text}
        onChange={(e) => setText(e.target.value)}
        rows={3}
        maxLength={4000}
        placeholder="What did you check? What did you find?"
        className="w-full rounded-lg border border-line bg-surface px-3 py-2 text-sm"
      />
      <div className="mt-2 flex items-center gap-3">
        <Button busy={busy} disabled={!text.trim()} onClick={() => void add()} icon={<Plus className="h-4 w-4" aria-hidden />}>Add note</Button>
        {error && <p role="alert" className="text-sm text-danger">{error}</p>}
      </div>
      {notes.length > 0 ? (
        <ul className="mt-4 space-y-3">
          {notes.map((n) => (
            <li key={n.id} className="rounded-lg border border-line p-3">
              <p className="whitespace-pre-wrap break-words text-sm">{n.body}</p>
              <div className="mt-2 flex items-center justify-between gap-2">
                <time className="text-xs text-muted" dateTime={n.created_at}>{formatTime(n.created_at, false)} UTC</time>
                <ConfirmButton label="Delete note" icon={<Trash2 className="h-4 w-4" aria-hidden />} onConfirm={() => remove(n.id)} />
              </div>
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-3 text-sm text-muted">No notes yet.</p>
      )}
    </Card>
  );
}

