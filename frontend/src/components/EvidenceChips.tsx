import { useState } from "react";
import { useRecordViewer } from "./RecordViewer";

/** Links to the log records a statement is based on. Each one opens the record. */
export function EvidenceChips({ ids, max = 5, label = "Evidence" }: { ids: number[]; max?: number; label?: string }) {
  const viewer = useRecordViewer();
  const [all, setAll] = useState(false);
  if (ids.length === 0) return null;
  const shown = all ? ids : ids.slice(0, max);
  return (
    <span className="inline-flex flex-wrap items-center gap-1 align-middle">
      <span className="text-xs text-muted">{label}:</span>
      {shown.map((id) => (
        <button
          key={id}
          type="button"
          onClick={() => viewer.open(id)}
          aria-label={`Open log record ${id}`}
          className="rounded border border-line bg-surface px-1.5 py-0.5 font-mono text-xs text-ocean-700 hover:bg-ocean-50"
        >
          #{id}
        </button>
      ))}
      {!all && ids.length > max && (
        <button type="button" onClick={() => setAll(true)} className="text-xs text-ocean-700 underline">
          +{ids.length - max} more
        </button>
      )}
    </span>
  );
}
