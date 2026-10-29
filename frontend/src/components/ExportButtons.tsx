import { useState } from "react";
import { Download } from "lucide-react";
import { api, type ExportFormat } from "../api/endpoints";
import { errorMessage } from "../api/client";
import { Button } from "./ui/Button";

const LABEL: Record<ExportFormat, string> = { md: "Markdown", json: "JSON", csv: "CSV" };

/** Download an incident (kind="incident") or the whole report (kind="report"). Failures are shown, not swallowed. */
export function ExportButtons({ kind, id, formats = ["md", "json", "csv"] }: { kind: "incident" | "report"; id: string; formats?: ExportFormat[] }) {
  const [busy, setBusy] = useState<ExportFormat | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function run(format: ExportFormat) {
    setBusy(format);
    setError(null);
    try {
      if (kind === "incident") await api.exportIncident(id, format);
      else await api.exportReport(id, format);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="flex flex-col gap-1">
      <div className="flex flex-wrap gap-2">
        {formats.map((format) => (
          <Button key={format} variant="secondary" busy={busy === format} onClick={() => void run(format)} icon={<Download className="h-4 w-4" aria-hidden />}>
            {LABEL[format]}
          </Button>
        ))}
      </div>
      {error && <p role="alert" className="text-sm text-danger">{error}</p>}
    </div>
  );
}
