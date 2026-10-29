import { Link } from "react-router-dom";
import { useApp } from "../../context/AppContext";
import { formatNumber } from "../../lib/format";
import { Badge } from "../ui/Badge";

/** Choose which loaded log file every page works on. */
export function SourcePicker() {
  const { sources, selected, select, loading } = useApp();
  if (loading) return <p className="text-sm text-muted">Loading...</p>;
  if (sources.length === 0) {
    return (
      <p className="text-sm text-muted">
        No log source yet. <Link to="/" className="font-medium text-ocean-700 underline">Load one</Link>
      </p>
    );
  }
  return (
    <div className="flex min-w-0 flex-wrap items-center gap-2">
      <label htmlFor="source-picker" className="text-sm font-medium text-ink">Log source</label>
      <select
        id="source-picker"
        value={selected?.id ?? ""}
        onChange={(e) => select(e.target.value)}
        className="min-w-0 max-w-[16rem] rounded-lg border border-line bg-surface px-2.5 py-1.5 text-sm text-ink"
      >
        {sources.map((s) => (
          <option key={s.id} value={s.id}>{s.name} · {formatNumber(s.record_count)} records</option>
        ))}
      </select>
      {selected?.kind === "sample" && <Badge tone="info" title="Invented data made for demonstration">Synthetic sample</Badge>}
    </div>
  );
}
