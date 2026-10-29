import { createContext, useCallback, useContext, useState, type ReactNode } from "react";
import { api } from "../api/endpoints";
import { useAsync } from "../hooks/useAsync";
import { formatNumber, formatTime } from "../lib/format";
import type { LogRecord } from "../api/types";
import { Drawer } from "./Drawer";
import { LevelBadge } from "./ui/Badge";
import { ErrorState, LoadingState } from "./ui/States";

// One drawer for the whole app: any evidence link calls open(id) and the same panel shows the record with its neighbours.
interface Viewer {
  open: (recordId: number) => void;
}
const ViewerContext = createContext<Viewer>({ open: () => undefined });

export function useRecordViewer(): Viewer {
  return useContext(ViewerContext);
}

export function RecordViewerProvider({ children }: { children: ReactNode }) {
  const [recordId, setRecordId] = useState<number | null>(null);
  const open = useCallback((id: number) => setRecordId(id), []);
  return (
    <ViewerContext.Provider value={{ open }}>
      {children}
      {recordId !== null && (
        <Drawer title={`Log record #${recordId}`} onClose={() => setRecordId(null)}>
          <RecordPanel recordId={recordId} onJump={setRecordId} />
        </Drawer>
      )}
    </ViewerContext.Provider>
  );
}

function NeighbourRow({ record, onJump }: { record: LogRecord; onJump: (id: number) => void }) {
  return (
    <button type="button" onClick={() => onJump(record.id)} className="flex w-full items-start gap-2 rounded px-2 py-1 text-left text-xs hover:bg-ocean-50">
      <span className="w-14 shrink-0 tabular-nums text-muted">line {record.line_no}</span>
      <LevelBadge level={record.level} />
      <span className="min-w-0 break-words font-mono text-ink">{record.message}</span>
    </button>
  );
}

function Field({ label, value }: { label: string; value: ReactNode }) {
  if (value === null || value === undefined || value === "") return null;
  return (
    <div className="min-w-0">
      <dt className="text-xs font-medium uppercase tracking-wide text-muted">{label}</dt>
      <dd className="break-words text-sm text-ink">{value}</dd>
    </div>
  );
}

function RecordPanel({ recordId, onJump }: { recordId: number; onJump: (id: number) => void }) {
  const { data, error, loading, reload } = useAsync((signal) => api.logDetail(recordId, 4, signal), [recordId]);
  if (loading) return <LoadingState label="Loading record..." />;
  if (error || !data) return <ErrorState message={error ?? "The record could not be loaded."} onRetry={reload} />;
  const { record, context } = data;
  return (
    <div className="space-y-4">
      <p className="text-xs text-muted">Log text below is shown exactly as written in the file. It is data and is never run or obeyed.</p>
      <dl className="grid grid-cols-2 gap-3">
        <Field label="Time (UTC)" value={formatTime(record.timestamp)} />
        <Field label="Level" value={<LevelBadge level={record.level} />} />
        <Field label="Service" value={record.service} />
        <Field label="Line in file" value={formatNumber(record.line_no)} />
        <Field label="Host" value={record.host} />
        <Field label="Request id" value={record.request_id} />
        <Field label="Endpoint" value={record.endpoint} />
        <Field label="HTTP status" value={record.http_status} />
        <Field label="Duration" value={record.latency_ms !== null ? `${formatNumber(record.latency_ms)} ms` : null} />
        <Field label="Exception" value={record.exception_type} />
        <Field label="Route" value={record.route_id} />
        <Field label="Trace id" value={record.trace_id} />
      </dl>
      <div>
        <h3 className="mb-1 text-sm font-semibold">Message</h3>
        <pre className="whitespace-pre-wrap break-words rounded-lg bg-slate-100 p-3 font-mono text-xs">{record.message}</pre>
      </div>
      {record.stack_trace && (
        <div>
          <h3 className="mb-1 text-sm font-semibold">Stack trace</h3>
          <pre className="max-h-64 overflow-auto whitespace-pre-wrap break-words rounded-lg bg-slate-100 p-3 font-mono text-xs">{record.stack_trace}</pre>
        </div>
      )}
      <div>
        <h3 className="mb-1 text-sm font-semibold">Original line</h3>
        <pre className="max-h-40 overflow-auto whitespace-pre-wrap break-words rounded-lg bg-slate-100 p-3 font-mono text-xs">{record.raw_line}</pre>
      </div>
      <div>
        <h3 className="mb-1 text-sm font-semibold">Records around it</h3>
        <div className="rounded-lg border border-line py-1">
          {context.before.map((r) => <NeighbourRow key={r.id} record={r} onJump={onJump} />)}
          <div className="bg-ocean-50 px-2 py-1 text-xs font-medium text-ocean-800">This record (line {record.line_no})</div>
          {context.after.map((r) => <NeighbourRow key={r.id} record={r} onJump={onJump} />)}
        </div>
      </div>
    </div>
  );
}
