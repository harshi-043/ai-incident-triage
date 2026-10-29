import { api } from "../../api/endpoints";
import { useAsync } from "../../hooks/useAsync";

/** Small live indicator of the backend, read from GET /api/health. */
export function HealthDot() {
  const { data, error, loading } = useAsync((signal) => api.health(signal), []);
  const ok = data?.status === "ok";
  const label = loading ? "Checking API..." : error ? "API not reachable" : ok ? `API online · v${data.version}` : "API degraded";
  const color = loading ? "bg-slate-300" : ok ? "bg-emerald-400" : error ? "bg-red-400" : "bg-amber-400";
  return (
    <p role="status" className="mt-4 flex items-center gap-2 px-2 text-xs text-nav-soft">
      <span className={`h-2 w-2 rounded-full ${color}`} aria-hidden />
      {label}
    </p>
  );
}
