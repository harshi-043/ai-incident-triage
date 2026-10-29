import { useEffect, useState } from "react";
import { api } from "../api/endpoints";
import { useApp } from "../context/AppContext";
import { useAsync } from "../hooks/useAsync";
import { useDebounced } from "../hooks/useDebounced";
import { formatNumber, formatTime } from "../lib/format";
import type { LogRecord } from "../api/types";
import { AnalysisGate } from "../components/AnalysisGate";
import { LoadLogsPanel } from "../components/LoadLogsPanel";
import { QualityReport } from "../components/QualityReport";
import { useRecordViewer } from "../components/RecordViewer";
import { LevelBadge } from "../components/ui/Badge";
import { Card, PageHeader } from "../components/ui/Card";
import { DataTable, type Column } from "../components/ui/DataTable";
import { ChipGroup, SelectField, TextField } from "../components/ui/Fields";
import { Pagination } from "../components/ui/Pagination";
import { ErrorState, LoadingState } from "../components/ui/States";

const PAGE_SIZE = 50;

export function LogExplorerPage() {
  return (
    <>
      <PageHeader title="Log Explorer" description="Search and filter the raw records. Open any row to see the full message, the stack trace and the lines around it." />
      <AnalysisGate needsAnalysis={false}>
        <Explorer />
      </AnalysisGate>
    </>
  );
}

function Explorer() {
  const { selected } = useApp();
  const viewer = useRecordViewer();
  const sourceId = selected!.id;
  const [search, setSearch] = useState("");
  const q = useDebounced(search);
  const [levels, setLevels] = useState<string[]>([]);
  const [service, setService] = useState("");
  const [sort, setSort] = useState("timestamp");
  const [order, setOrder] = useState<"asc" | "desc">("asc");
  const [page, setPage] = useState(1);

  // A new filter always starts from the first page.
  useEffect(() => setPage(1), [q, levels, service, sort, order, sourceId]);
  useEffect(() => {
    setSearch(""); setLevels([]); setService("");
  }, [sourceId]);

  const detail = useAsync((signal) => api.sourceDetail(sourceId, signal), [sourceId]);
  const logs = useAsync(
    (signal) => api.logs({ source_id: sourceId, q, level: levels, service: service ? [service] : [], sort, order, page, page_size: PAGE_SIZE }, signal),
    [sourceId, q, levels, service, sort, order, page],
  );

  const columns: Column<LogRecord>[] = [
    { key: "timestamp", label: "Time (UTC)", sortable: true, render: (r) => <span className="font-mono text-xs">{formatTime(r.timestamp)}</span> },
    { key: "level", label: "Level", sortable: true, render: (r) => <LevelBadge level={r.level} /> },
    { key: "service", label: "Service", sortable: true },
    { key: "message", label: "Message", render: (r) => <span className="block max-w-xl truncate font-mono text-xs" title={r.message}>{r.message}</span> },
    { key: "http_status", label: "Status", sortable: true, align: "right", render: (r) => r.http_status ?? "—" },
    { key: "latency_ms", label: "Duration", sortable: true, align: "right", render: (r) => (r.latency_ms !== null ? `${formatNumber(r.latency_ms)} ms` : "—") },
  ];

  const onSort = (key: string) => {
    if (key === sort) setOrder(order === "asc" ? "desc" : "asc");
    else { setSort(key); setOrder("asc"); }
  };

  const totalPages = logs.data ? Math.max(1, Math.ceil(logs.data.total / PAGE_SIZE)) : 1;

  return (
    <div className="space-y-5">
      {detail.data && <QualityReport quality={detail.data.quality} />}
      {detail.error && <ErrorState message={detail.error} onRetry={detail.reload} />}

      <Card>
        <div className="grid gap-3 md:grid-cols-3">
          <TextField label="Search" type="search" value={search} onChange={setSearch} placeholder="message, request id, exception, service" />
          <SelectField
            label="Service"
            value={service}
            onChange={setService}
            options={[{ value: "", label: "All services" }, ...(detail.data?.filters.services ?? []).map((s) => ({ value: s, label: s }))]}
          />
          <ChipGroup
            label="Level"
            selected={levels}
            onChange={setLevels}
            options={(detail.data?.filters.levels ?? ["INFO", "WARNING", "ERROR"]).map((l) => ({ value: l, label: l }))}
          />
        </div>
      </Card>

      {logs.error && <ErrorState message={logs.error} onRetry={logs.reload} />}
      {logs.loading && !logs.data && <LoadingState label="Loading records..." />}
      {logs.data && (
        <div className={logs.loading ? "opacity-60" : ""}>
          <DataTable
            caption="Log records"
            columns={columns}
            rows={logs.data.items}
            rowKey={(r) => String(r.id)}
            sortBy={sort}
            sortDir={order}
            onSort={onSort}
            onRowClick={(r) => viewer.open(r.id)}
            emptyText="No records match these filters."
          />
          <Pagination page={page} totalPages={totalPages} total={logs.data.total} pageSize={PAGE_SIZE} onPage={setPage} noun="records" />
        </div>
      )}

      <details className="rounded-xl border border-line bg-surface p-4">
        <summary className="cursor-pointer text-sm font-medium text-ocean-700">Load another log file</summary>
        <div className="mt-3"><LoadLogsPanel /></div>
      </details>
    </div>
  );
}
