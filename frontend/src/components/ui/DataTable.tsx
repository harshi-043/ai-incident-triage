import type { ReactNode } from "react";
import { ArrowDown, ArrowUp, ChevronsUpDown } from "lucide-react";
import { formatCell } from "../../lib/format";

export interface Column<T> {
  key: string;
  label: string;
  sortable?: boolean;
  align?: "left" | "right";
  render?: (row: T) => ReactNode;
}

interface Props<T> {
  columns: Column<T>[];
  rows: T[];
  rowKey: (row: T) => string;
  caption: string;
  sortBy?: string;
  sortDir?: "asc" | "desc";
  onSort?: (key: string) => void;
  onRowClick?: (row: T) => void;
  emptyText?: string;
}

/** A plain accessible table. Sorting is done by the server; this only shows the arrows and reports clicks. */
export function DataTable<T extends object>({
  columns,
  rows,
  rowKey,
  caption,
  sortBy,
  sortDir,
  onSort,
  onRowClick,
  emptyText = "No rows to show.",
}: Props<T>) {
  return (
    <div className="overflow-x-auto rounded-lg border border-line">
      <table className="min-w-full text-left text-sm">
        <caption className="sr-only">{caption}</caption>
        <thead className="bg-slate-100 text-xs uppercase tracking-wide text-muted">
          <tr>
            {columns.map((col) => {
              const active = sortBy === col.key;
              return (
                <th
                  key={col.key}
                  scope="col"
                  aria-sort={active ? (sortDir === "asc" ? "ascending" : "descending") : undefined}
                  className={`whitespace-nowrap px-3 py-2 font-medium ${col.align === "right" ? "text-right" : ""}`}
                >
                  {col.sortable && onSort ? (
                    <button
                      type="button"
                      onClick={() => onSort(col.key)}
                      className="inline-flex items-center gap-1 uppercase tracking-wide hover:text-ink"
                    >
                      {col.label}
                      {active ? (
                        sortDir === "asc" ? <ArrowUp className="h-3 w-3" aria-hidden /> : <ArrowDown className="h-3 w-3" aria-hidden />
                      ) : (
                        <ChevronsUpDown className="h-3 w-3 opacity-40" aria-hidden />
                      )}
                    </button>
                  ) : (
                    col.label
                  )}
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody className="divide-y divide-line bg-surface">
          {rows.length === 0 ? (
            <tr>
              <td colSpan={columns.length} className="px-3 py-8 text-center text-muted">
                {emptyText}
              </td>
            </tr>
          ) : (
            rows.map((row) => (
              <tr
                key={rowKey(row)}
                className={onRowClick ? "cursor-pointer hover:bg-ocean-50" : ""}
                onClick={onRowClick ? () => onRowClick(row) : undefined}
                onKeyDown={onRowClick ? (e) => e.key === "Enter" && onRowClick(row) : undefined}
                tabIndex={onRowClick ? 0 : undefined}
              >
                {columns.map((col) => (
                  <td key={col.key} className={`whitespace-nowrap px-3 py-2 tabular-nums ${col.align === "right" ? "text-right" : ""}`}>
                    {col.render ? col.render(row) : formatCell((row as Record<string, unknown>)[col.key])}
                  </td>
                ))}
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}
