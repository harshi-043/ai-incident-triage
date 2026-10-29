import { CheckCircle2, Info, TriangleAlert } from "lucide-react";
import type { Quality } from "../api/types";
import { formatNumber, formatPercent, humanize } from "../lib/format";
import { Card, CardHeader } from "./ui/Card";

const COVERAGE_LABEL: Record<string, string> = {
  timestamp: "Time", service: "Service", host: "Host", request_id: "Request id", trace_id: "Trace id", route_id: "Route id",
  http_status: "HTTP status", latency_ms: "Duration", exception_type: "Exception type",
};

/** What the file contained and what could not be used. Shown so nobody trusts incomplete data by accident. */
export function QualityReport({ quality }: { quality: Quality }) {
  const cleanFile = quality.warnings.length === 0;
  return (
    <Card>
      <CardHeader
        title="Data quality"
        subtitle={`${quality.format.toUpperCase()} file, ${quality.encoding}, ${formatNumber(quality.total_lines)} lines read.`}
      />
      <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {[
          ["Records stored", quality.stored_records],
          ["Lines that could not be read", quality.rejected_count],
          ["Duplicates removed", quality.duplicates_removed],
          ["Records without a time", quality.missing_timestamp],
        ].map(([label, value]) => (
          <div key={label as string}>
            <dt className="text-xs text-muted">{label}</dt>
            <dd className="text-lg font-semibold tabular-nums">{formatNumber(value as number)}</dd>
          </div>
        ))}
      </dl>

      <h3 className="mb-1.5 mt-4 text-sm font-semibold">How complete each field is</h3>
      <ul className="grid gap-x-6 gap-y-1.5 sm:grid-cols-2">
        {Object.entries(quality.coverage).map(([field, share]) => (
          <li key={field} className="flex items-center gap-2 text-sm">
            <span className="w-28 shrink-0 text-muted">{COVERAGE_LABEL[field] ?? humanize(field)}</span>
            <span className="h-2 flex-1 overflow-hidden rounded-full bg-slate-100" aria-hidden>
              <span className="block h-full rounded-full bg-ocean-600" style={{ width: `${Math.round(share * 100)}%` }} />
            </span>
            <span className="w-10 text-right tabular-nums text-muted">{formatPercent(share)}</span>
          </li>
        ))}
      </ul>
      <p className="mt-1 text-xs text-muted">Low numbers are normal for fields a log does not carry (for example a route id in an application log).</p>

      <h3 className="mb-1.5 mt-4 text-sm font-semibold">Notes</h3>
      {cleanFile ? (
        <p className="flex items-center gap-2 text-sm text-ok"><CheckCircle2 className="h-4 w-4" aria-hidden /> No problems were found while reading this file.</p>
      ) : (
        <ul className="space-y-1.5">
          {quality.warnings.map((w) => (
            <li key={w.code} className="flex items-start gap-2 text-sm">
              {w.severity === "info" ? <Info className="mt-0.5 h-4 w-4 shrink-0 text-ocean-600" aria-hidden /> : <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0 text-warn" aria-hidden />}
              <span>{w.message} <span className="font-medium tabular-nums">({formatNumber(w.count)})</span></span>
            </li>
          ))}
        </ul>
      )}
      {quality.rejected_examples.length > 0 && (
        <details className="mt-3 text-sm">
          <summary className="cursor-pointer font-medium text-ocean-700">Show examples of lines that were left out</summary>
          <ul className="mt-2 space-y-1">
            {quality.rejected_examples.map((r) => (
              <li key={r.line_no} className="break-words font-mono text-xs"><span className="text-muted">line {r.line_no}:</span> {r.snippet} <span className="text-muted">({r.reason})</span></li>
            ))}
          </ul>
        </details>
      )}
    </Card>
  );
}
