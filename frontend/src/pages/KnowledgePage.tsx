import { useRef, useState, type FormEvent } from "react";
import { FlaskConical, Search, Trash2, Upload } from "lucide-react";
import { api } from "../api/endpoints";
import { errorMessage } from "../api/client";
import { useAsync } from "../hooks/useAsync";
import type { SearchResult } from "../api/types";
import { ConfirmButton } from "../components/ConfirmButton";
import { Drawer } from "../components/Drawer";
import { RunbookHitCard } from "../components/RunbookHitCard";
import { Badge } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";
import { Card, CardHeader, PageHeader } from "../components/ui/Card";
import { EmptyState, ErrorState, LoadingState, Note } from "../components/ui/States";
import { formatBytes, formatTime } from "../lib/format";

export function KnowledgePage() {
  const status = useAsync((signal) => api.knowledgeStatus(signal), []);
  const docs = useAsync((signal) => api.documents(signal), []);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [viewing, setViewing] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  function reloadAll() {
    status.reload();
    docs.reload();
  }

  async function run(key: string, work: () => Promise<string | void>) {
    setBusy(key);
    setError(null);
    setMessage(null);
    try {
      const text = await work();
      if (text) setMessage(text);
      reloadAll();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(null);
    }
  }

  const retrieval = status.data?.retrieval;
  const items = docs.data?.items ?? [];

  return (
    <>
      <PageHeader
        title="Knowledge Base"
        description="Runbooks and notes that the assistant searches. Their text is shown as written. Commands inside them are displayed for a person to read and are never run."
        action={
          <div className="flex flex-wrap gap-2">
            <input
              ref={fileRef}
              type="file"
              accept=".md,.markdown,.txt,.pdf"
              className="sr-only"
              aria-label="Choose a runbook file"
              onChange={(e) => {
                const file = e.target.files?.[0];
                e.target.value = "";
                if (file) void run("upload", async () => { const r = await api.uploadRunbook(file); return r.created ? `Added "${r.document.title}".` : `"${r.document.title}" was already in the knowledge base.`; });
              }}
            />
            <Button busy={busy === "upload"} onClick={() => fileRef.current?.click()} icon={<Upload className="h-4 w-4" aria-hidden />}>Upload a runbook</Button>
            <Button variant="secondary" busy={busy === "samples"} icon={<FlaskConical className="h-4 w-4" aria-hidden />}
              onClick={() => void run("samples", async () => { const r = await api.loadSampleRunbooks(); return `${r.created} sample runbook(s) added. ${r.note}`; })}>
              Load sample runbooks
            </Button>
          </div>
        }
      />

      {error && <div className="mb-4"><Note tone="danger">{error}</Note></div>}
      {message && <div className="mb-4" role="status"><Note>{message}</Note></div>}

      <div className="space-y-5">
        <Card>
          <CardHeader title="Search status" />
          {status.loading && !status.data ? <LoadingState /> : status.error ? <ErrorState message={status.error} onRetry={status.reload} /> : status.data && (
            <div className="space-y-2 text-sm">
              <p className="flex flex-wrap items-center gap-2">
                <Badge tone="neutral">{status.data.documents} documents</Badge>
                <Badge tone="neutral">{status.data.chunks} sections</Badge>
                <Badge tone="info">Method: {retrieval?.backend}</Badge>
                <Badge tone="neutral">Index: {retrieval?.vector_store}</Badge>
                <Badge tone="neutral" title="Matches scoring below this are treated as 'no relevant source'.">Minimum match {retrieval?.min_relevance}</Badge>
              </p>
              {retrieval?.fallback && <Note tone="warn">The requested search method ({retrieval.requested_backend}) is not in use. {retrieval.fallback_reason} Keyword search (TF-IDF) is used instead.</Note>}
            </div>
          )}
        </Card>

        <Card>
          <CardHeader title="Documents" />
          {docs.loading && !docs.data ? <LoadingState /> : docs.error ? <ErrorState message={docs.error} onRetry={docs.reload} /> : items.length === 0 ? (
            <EmptyState title="The knowledge base is empty">Upload a runbook (.md or .txt), or load the sample runbooks. They are synthetic examples written for this demo. Without documents, the assistant says "no relevant source".</EmptyState>
          ) : (
            <ul className="divide-y divide-line">
              {items.map((d) => (
                <li key={d.id} className="flex flex-wrap items-center justify-between gap-2 py-2.5">
                  <div className="min-w-0">
                    <button type="button" onClick={() => setViewing(d.id)} className="break-words text-left text-sm font-medium text-ocean-700 underline">{d.title}</button>
                    <p className="text-xs text-muted">{d.filename} · {formatBytes(d.size_bytes)} · {d.chunk_count} sections · {d.kind === "sample" ? "sample (synthetic)" : "uploaded"} · {formatTime(d.created_at, false)} UTC</p>
                  </div>
                  <ConfirmButton label={`Delete ${d.title}`} icon={<Trash2 className="h-4 w-4" aria-hidden />} busy={busy === `del-${d.id}`}
                    onConfirm={() => run(`del-${d.id}`, async () => { await api.deleteDocument(d.id); return `Deleted "${d.title}".`; })} />
                </li>
              ))}
            </ul>
          )}
        </Card>

        <SearchBox />
      </div>

      {viewing && <DocumentDrawer id={viewing} onClose={() => setViewing(null)} />}
    </>
  );
}

function SearchBox() {
  const [query, setQuery] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<SearchResult | null>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (query.trim().length < 2) return;
    setBusy(true);
    setError(null);
    try {
      setResult(await api.searchRunbooks(query.trim()));
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardHeader title="Try a search" subtitle="See what the assistant would retrieve for a question." />
      <form onSubmit={submit} className="flex flex-wrap gap-2">
        <label htmlFor="kb-search" className="sr-only">Search the knowledge base</label>
        <input id="kb-search" value={query} onChange={(e) => setQuery(e.target.value)} maxLength={500} placeholder="For example: database connection pool exhausted"
          className="min-w-0 flex-1 rounded-lg border border-line bg-surface px-3 py-2 text-sm" />
        <Button type="submit" busy={busy} disabled={query.trim().length < 2} icon={<Search className="h-4 w-4" aria-hidden />}>Search</Button>
      </form>
      {error && <p role="alert" className="mt-3 text-sm text-danger">{error}</p>}
      {result && (
        <div className="mt-4 space-y-3" aria-live="polite">
          {result.no_relevant_source ? (
            <Note tone="warn">{result.message ?? "No relevant source was found in the knowledge base for this question."}</Note>
          ) : result.results.map((r) => <RunbookHitCard key={r.chunk_id} citation={r.citation} relevance={r.relevance} text={r.text} commands={r.documented_commands} />)}
        </div>
      )}
    </Card>
  );
}

function DocumentDrawer({ id, onClose }: { id: string; onClose: () => void }) {
  const doc = useAsync((signal) => api.document(id, signal), [id]);
  return (
    <Drawer title={doc.data?.document.title ?? "Document"} onClose={onClose}>
      {doc.loading ? <LoadingState /> : doc.error ? <ErrorState message={doc.error} onRetry={doc.reload} /> : doc.data && (
        <div className="space-y-3">
          <Note>Shown as plain text. Nothing in this document is run.</Note>
          <pre className="whitespace-pre-wrap break-words rounded-lg border border-line bg-paper p-3 text-sm text-ink">{doc.data.text}</pre>
        </div>
      )}
    </Drawer>
  );
}
