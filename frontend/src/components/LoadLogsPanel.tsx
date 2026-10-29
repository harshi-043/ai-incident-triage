import { useEffect, useRef, useState } from "react";
import { FlaskConical, Upload } from "lucide-react";
import { api } from "../api/endpoints";
import { errorMessage } from "../api/client";
import { useApp } from "../context/AppContext";
import { useAsync } from "../hooks/useAsync";
import type { IngestResult } from "../api/types";
import { Button } from "./ui/Button";
import { Note } from "./ui/States";

/** Load logs: upload a file, or load one of the built-in SYNTHETIC samples. */
export function LoadLogsPanel({ onLoaded }: { onLoaded?: (result: IngestResult) => void }) {
  const { refresh } = useApp();
  const samples = useAsync((signal) => api.samples(signal), []);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<IngestResult | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const mounted = useRef(true);
  useEffect(() => () => { mounted.current = false; }, []);

  async function finish(promise: Promise<IngestResult>, key: string) {
    setBusy(key);
    setError(null);
    try {
      const res = await promise;
      await refresh(res.source.id);
      if (!mounted.current) return;
      setResult(res);
      onLoaded?.(res);
    } catch (err) {
      if (mounted.current) setError(errorMessage(err));
    } finally {
      if (mounted.current) setBusy(null);
    }
  }

  return (
    <div className="space-y-3 text-left">
      <div className="flex flex-wrap items-center gap-2">
        <input
          ref={fileRef}
          type="file"
          accept=".csv,.txt,.log,.json,.jsonl,.ndjson"
          className="sr-only"
          aria-label="Choose a log file"
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) void finish(api.uploadLog(file), "upload");
            e.target.value = "";
          }}
        />
        <Button busy={busy === "upload"} onClick={() => fileRef.current?.click()} icon={<Upload className="h-4 w-4" aria-hidden />}>
          Upload a log file
        </Button>
        {(samples.data?.items ?? []).map((sample) => (
          <Button
            key={sample.name}
            variant="secondary"
            busy={busy === sample.name}
            onClick={() => void finish(api.loadSample(sample.name), sample.name)}
            icon={<FlaskConical className="h-4 w-4" aria-hidden />}
            title={sample.description}
          >
            Load sample: {sample.title.split(" (")[0]}
          </Button>
        ))}
      </div>
      <p className="text-xs text-muted">Accepted: CSV, TXT, LOG, JSON, JSONL. Samples are synthetic and invented for demonstration.</p>
      {samples.error && <Note tone="warn">The sample list could not be loaded: {samples.error}</Note>}
      {error && <p role="alert" className="text-sm text-danger">{error}</p>}
      {result && (
        <Note>
          {result.already_ingested ? "This exact file was already loaded, so the existing copy is selected." : `Loaded ${result.source.record_count.toLocaleString("en-US")} records from ${result.source.name}.`}
          {result.quality.warnings.length > 0 && ` ${result.quality.warnings.length} data-quality note(s) are shown in the Log Explorer.`}
        </Note>
      )}
    </div>
  );
}
