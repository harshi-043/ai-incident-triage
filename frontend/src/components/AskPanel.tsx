import { useState, type FormEvent } from "react";
import { Send } from "lucide-react";
import { api } from "../api/endpoints";
import { errorMessage } from "../api/client";
import type { Answer } from "../api/types";
import { formatTime } from "../lib/format";
import { EvidenceChips } from "./EvidenceChips";
import { RunbookHitCard } from "./RunbookHitCard";
import { LevelBadge, OriginBadge } from "./ui/Badge";
import { Button } from "./ui/Button";
import { Card, CardHeader } from "./ui/Card";
import { Note } from "./ui/States";

/** Ask a question about one incident. Without AI the answer is a search result (records and runbook sections that match). */
export function AskPanel({ incidentId, useAi }: { incidentId: string; useAi: boolean }) {
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [answer, setAnswer] = useState<Answer | null>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (question.trim().length < 3) return;
    setBusy(true);
    setError(null);
    try {
      setAnswer(await api.ask(incidentId, question.trim(), useAi));
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardHeader title="Ask about this incident" subtitle={useAi ? "The AI provider will be asked, using only this incident's evidence." : "Finds the log records and runbook sections that match your question."} />
      <form onSubmit={submit} className="flex flex-wrap gap-2">
        <label htmlFor="ask-input" className="sr-only">Your question</label>
        <input
          id="ask-input"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          maxLength={500}
          placeholder="For example: which service failed first?"
          className="min-w-0 flex-1 rounded-lg border border-line bg-surface px-3 py-2 text-sm"
        />
        <Button type="submit" busy={busy} disabled={question.trim().length < 3} icon={<Send className="h-4 w-4" aria-hidden />}>Ask</Button>
      </form>
      {error && <p role="alert" className="mt-3 text-sm text-danger">{error}</p>}
      {answer && (
        <div className="mt-4 space-y-3" aria-live="polite">
          {answer.ai_error && <Note tone="warn">The AI provider could not be used: {answer.ai_error}</Note>}
          <div className="flex flex-wrap items-center gap-2"><OriginBadge origin={answer.answer_origin === "retrieval" ? "observed" : "ai_hypothesis"} /></div>
          <p className="whitespace-pre-wrap break-words text-sm text-ink">{answer.answer}</p>
          {answer.uncertainty && <p className="text-sm text-muted">Not known: {answer.uncertainty}</p>}
          {answer.evidence.length > 0 && (
            <div>
              <h3 className="mb-1 text-sm font-semibold">Matching log records</h3>
              <ul className="space-y-1.5">
                {answer.evidence.map((e) => (
                  <li key={e.id} className="flex flex-wrap items-start gap-2 text-xs">
                    <EvidenceChips ids={[e.id]} label="" />
                    <LevelBadge level={e.level} />
                    <span className="text-muted">{formatTime(e.timestamp)}</span>
                    <span className="min-w-0 break-words font-mono text-ink">{e.service}: {e.message}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
          {answer.runbook_sources.length > 0 && (
            <div className="space-y-2">
              <h3 className="text-sm font-semibold">Matching runbook sections</h3>
              {answer.runbook_sources.map((s, i) => <RunbookHitCard key={i} citation={s.citation} relevance={s.relevance} text={s.text} />)}
            </div>
          )}
        </div>
      )}
    </Card>
  );
}
