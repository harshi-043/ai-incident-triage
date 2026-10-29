import type { ReactNode } from "react";
import { AlertTriangle, Loader2 } from "lucide-react";
import { Button } from "./Button";

export function LoadingState({ label = "Loading..." }: { label?: string }) {
  return (
    <div role="status" className="flex items-center justify-center gap-2 rounded-xl border border-line bg-surface p-10 text-sm text-muted">
      <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
      {label}
    </div>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div role="alert" className="flex flex-wrap items-center gap-3 rounded-xl border border-danger/30 bg-danger-bg p-4 text-sm text-danger">
      <AlertTriangle className="h-5 w-5 shrink-0" aria-hidden />
      <p className="min-w-0 flex-1">{message}</p>
      {onRetry && (
        <Button variant="secondary" onClick={onRetry}>
          Try again
        </Button>
      )}
    </div>
  );
}

export function EmptyState({ title, children, action }: { title: string; children?: ReactNode; action?: ReactNode }) {
  return (
    <div className="rounded-xl border border-dashed border-slate-300 bg-surface p-8 text-center">
      <h3 className="text-base font-semibold text-ink">{title}</h3>
      {children && <div className="mx-auto mt-1 max-w-xl text-sm text-muted">{children}</div>}
      {action && <div className="mt-4 flex justify-center">{action}</div>}
    </div>
  );
}

export function Note({ children, tone = "info" }: { children: ReactNode; tone?: "info" | "warn" | "danger" }) {
  const style =
    tone === "warn" ? "border-warn/30 bg-warn-bg text-warn" : tone === "danger" ? "border-danger/30 bg-danger-bg text-danger" : "border-ocean-100 bg-ocean-50 text-ocean-800";
  return <p className={`rounded-lg border px-3 py-2 text-sm ${style}`}>{children}</p>;
}
