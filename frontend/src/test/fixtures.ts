// Small made-up API answers for tests. All data here is invented for testing.
import type { Analysis, AppSettings, Incident, IncidentDetail, Source, Summary } from "../api/types";

export const source: Source = {
  id: "src1", name: "test-app.log", original_filename: "test-app.log", kind: "sample", format: "text",
  size_bytes: 2048, record_count: 120, created_at: "2026-01-01T10:00:00Z",
};

export const analysis: Analysis = {
  id: "an1", source_id: "src1",
  params: { similarity_threshold: 0.6, gap_minutes: 10, min_errors: 5, merge_across_services: false },
  stats: { incident_count: 1, group_count: 1 }, created_at: "2026-01-01T10:05:00Z",
};

export const incident: Incident = {
  id: "inc1", analysis_id: "an1", number: 1, label: "INC-1", title: "Database connection pool exhausted",
  severity: "high", status: "open", reviewed: false,
  first_seen: "2026-01-01T09:00:00Z", last_seen: "2026-01-01T09:20:00Z",
  record_count: 30, error_count: 25, services: ["payments"], top_patterns: [], updated_at: "2026-01-01T10:05:00Z",
};

export const incidentDetail: IncidentDetail = {
  incident, explanation: "25 errors in 20 minutes on payments.",
  detection: { peak_window_errors: 12, attached_warning_records: 3, context_events: 2, gap_minutes: 10 },
  timeline: [{ time: "2026-01-01T09:00:00Z", kind: "first_error", title: "First error", detail: "payments failed", origin: "observed", evidence_ids: [11] }],
  groups: [], representative_records: [], related_incidents: [], notes: [], source, labels: {},
};

export const settingsNoAi: AppSettings = {
  version: "0.1.0",
  ai: { provider: "none", model: null, key_set: false, ready: false, problem: "No AI provider is configured.", timeout_seconds: 30, max_evidence_records: 20 },
  retrieval: { embedding_backend: "tfidf", embedding_model: "all-MiniLM-L6-v2", chunk_size_chars: 900, chunk_overlap_chars: 120, min_relevance: 0.16 },
  detection_defaults: { similarity_threshold: 0.6, gap_minutes: 10, min_errors: 5 },
  limits: { max_upload_mb: 10, max_log_records: 50000, max_runbook_mb: 1 },
  privacy: "Logs stay on this server unless you turn on an AI provider.",
  safety: "This application never runs commands or changes systems.",
  how_to_change: "Set environment variables and restart the server.",
};

export const summaryNoSource: Summary = {
  incident_id: "inc1", incident_label: "INC-1", generated_by: "deterministic", used_ai: false, ai_error: null, ai_available: false,
  headline: "INC-1: 25 errors on payments",
  ai_narrative: null,
  facts: [{ statement: "25 error records were logged on payments.", evidence_ids: [11, 12], origin: "observed" }],
  retrieved: [], no_relevant_source: true,
  hypotheses: [{ statement: "A shared dependency may be failing.", reasoning: "All errors name the same host.", origin: "rule", strength: "moderate", evidence_ids: [11], caveat: "Not confirmed." }],
  steps: [{
    id: "s1", title: "Check the first error", instruction: "Read record 11 and its neighbours.", origin: "rule", strength: "moderate",
    strength_reason: "Based on the first error in the burst.", evidence_ids: [11], evidence_match: "specific", citation: null,
    expected_observation: "A connection error naming the host.", documented_commands: [], read_only: true,
  }],
  not_suggested: [], limitations: ["Only the loaded log was read."], created_at: "2026-01-01T10:10:00Z",
  notice: "Nothing was run. These are suggestions for a person to review.",
};
