import { ChevronLeft, ChevronRight } from "lucide-react";
import { formatNumber } from "../../lib/format";
import { Button } from "./Button";

export function Pagination({
  page,
  totalPages,
  total,
  pageSize,
  onPage,
  noun = "rows",
}: {
  page: number;
  totalPages: number;
  total: number;
  pageSize: number;
  onPage: (page: number) => void;
  noun?: string;
}) {
  const first = total === 0 ? 0 : (page - 1) * pageSize + 1;
  const last = Math.min(page * pageSize, total);
  return (
    <nav aria-label="Pagination" className="mt-3 flex flex-wrap items-center justify-between gap-2 text-sm text-muted">
      <p>
        {formatNumber(first)}&ndash;{formatNumber(last)} of {formatNumber(total)} {noun}
      </p>
      <div className="flex items-center gap-2">
        <Button variant="secondary" disabled={page <= 1} onClick={() => onPage(page - 1)} icon={<ChevronLeft className="h-4 w-4" aria-hidden />}>
          Previous
        </Button>
        <span aria-live="polite">
          Page {page} of {Math.max(totalPages, 1)}
        </span>
        <Button variant="secondary" disabled={page >= totalPages} onClick={() => onPage(page + 1)}>
          Next <ChevronRight className="h-4 w-4" aria-hidden />
        </Button>
      </div>
    </nav>
  );
}
