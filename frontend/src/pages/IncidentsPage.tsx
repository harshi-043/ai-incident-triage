import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api/endpoints";
import { useApp } from "../context/AppContext";
import { useAsync } from "../hooks/useAsync";
import { useDebounced } from "../hooks/useDebounced";
import { formatClock, formatNumber, formatTime } from "../lib/format";
import type { Incident } from "../api/types";
import { AnalysisGate } from "../components/AnalysisGate";
import { SeverityBadge, StatusBadge, STATUS_LABEL } from "../components/ui/Badge";
import { Card, PageHeader } from "../components/ui/Card";
import { DataTable, type Column } from "../components/ui/DataTable";
import { ChipGroup, SelectField, TextField } from "../components/ui/Fields";
import { Pagination } from "../components/ui/Pagination";
import { EmptyState, ErrorState, LoadingState } from "../components/ui/States";

const PAGE_SIZE = 25;
const SEVERITIES = ["critical", "high", "medium", "low"];

export function IncidentsPage() {
  return (
    <>
      <PageHeader title="Incidents" description="Bursts of related errors found in the log. Each one explains why it was flagged. Open an incident to see its timeline and evidence." />
      <AnalysisGate>
        <IncidentList />
      </AnalysisGate>
    </>
  );
}

function IncidentList() {
  const { analysis } = useApp();
  const navigate = useNavigate();
  const [search, setSearch] = useState("");
  const q = useDebounced(search);
  const [severity, setSeverity] = useState<string[]>([]);
  const [status, setStatus] = useState("");
  const [sort, setSort] = useState("severity");
  const [order, setOrder] = useState<"asc" | "desc">("asc");
  const [page, setPage] = useState(1);
  useEffect(() => setPage(1), [q, severity, status, sort, order, analysis?.id]);

  const { data, error, loading, reload } = useAsync(
    (signal) => api.incidents({ analysis_id: analysis!.id, q, severity, status: status ? [status] : [], sort, order, page, page_size: PAGE_SIZE }, signal),
    [analysis?.id, q, severity, status, sort, order, page],
  );

  const columns: Column<Incident>[] = [
    { key: "number", label: "ID", sortable: true, render: (i) => <span className="font-mono text-xs">{i.label}</span> },
    { key: "severity", label: "Severity", sortable: true, render: (i) => <SeverityBadge severity={i.severity} /> },
    { key: "title", label: "What happened", render: (i) => <span className="block max-w-md truncate" title={i.title}>{i.title}</span> },
    { key: "first_seen", label: "Window (UTC)", sortable: true, render: (i) => <span className="text-xs">{formatTime(i.first_seen, false)} – {formatClock(i.last_seen)}</span> },
    { key: "services", label: "Services", render: (i) => <span className="block max-w-[14rem] truncate" title={i.services.join(", ")}>{i.services.join(", ")}</span> },
    { key: "error_count", label: "Errors", sortable: true, align: "right", render: (i) => formatNumber(i.error_count) },
    { key: "status", label: "Status", sortable: true, render: (i) => <span className="inline-flex items-center gap-1.5"><StatusBadge status={i.status} />{i.reviewed && <span className="text-xs text-muted">reviewed</span>}</span> },
  ];
  const onSort = (key: string) => {
    if (key === sort) setOrder(order === "asc" ? "desc" : "asc");
    else { setSort(key); setOrder(key === "error_count" ? "desc" : "asc"); }
  };

  return (
    <div className="space-y-4">
      <Card>
        <div className="grid gap-3 md:grid-cols-3">
          <TextField label="Search" type="search" value={search} onChange={setSearch} placeholder="title or pattern" />
          <ChipGroup label="Severity" selected={severity} onChange={setSeverity} options={SEVERITIES.map((s) => ({ value: s, label: s.charAt(0).toUpperCase() + s.slice(1) }))} />
          <SelectField label="Status" value={status} onChange={setStatus} options={[{ value: "", label: "Any status" }, ...Object.entries(STATUS_LABEL).map(([value, label]) => ({ value, label }))]} />
        </div>
      </Card>
      {error && <ErrorState message={error} onRetry={reload} />}
      {loading && !data && <LoadingState label="Loading incidents..." />}
      {data && data.total === 0 && !loading && (
        <EmptyState title="No incidents match">
          {severity.length || status || q ? "Clear the filters to see all incidents." : "No bursts of errors were found with the current settings. On the Dashboard you can run the analysis again with a lower number of errors needed."}
        </EmptyState>
      )}
      {data && data.total > 0 && (
        <div className={loading ? "opacity-60" : ""}>
          <DataTable
            caption="Incidents"
            columns={columns}
            rows={data.items}
            rowKey={(i) => i.id}
            sortBy={sort}
            sortDir={order}
            onSort={onSort}
            onRowClick={(i) => navigate(`/incidents/${i.id}`)}
          />
          <Pagination page={page} totalPages={Math.max(1, Math.ceil(data.total / PAGE_SIZE))} total={data.total} pageSize={PAGE_SIZE} onPage={setPage} noun="incidents" />
        </div>
      )}
    </div>
  );
}
