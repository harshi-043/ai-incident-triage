// Shapes of the backend responses. They mirror the Pydantic models and dictionaries in the API.

export type Level = "DEBUG" | "INFO" | "WARNING" | "ERROR" | "CRITICAL";
export type Severity = "critical" | "high" | "medium" | "low";
export type Status = "open" | "investigating" | "resolved" | "ignored";
/** Where a statement came from. */
export type Origin = "observed" | "inferred" | "runbook" | "rule" | "ai_hypothesis";
export type Strength = "strong" | "moderate" | "weak";

export interface Health {
  status: string;
  version: string;
  checks: Record<string, string>;
  ai_provider: string;
  embedding_backend: string;
}

export interface Source {
  id: string;
  name: string;
  original_filename: string;
  kind: "upload" | "sample";
  format: string;
  size_bytes: number;
  record_count: number;
  created_at: string;
}

export interface QualityWarning {
  code: string;
  message: string;
  count: number;
  severity: "info" | "warning" | "error";
}

export interface Quality {
  format: string;
  encoding: string;
  total_lines: number;
  blank_lines: number;
  parsed_records: number;
  stored_records: number;
  rejected_count: number;
  duplicates_removed: number;
  missing_timestamp: number;
  coverage: Record<string, number>;
  warnings: QualityWarning[];
  rejected_examples: { line_no: number; reason: string; snippet: string }[];
}

export interface IngestResult {
  source: Source;
  quality: Quality;
  already_ingested: boolean;
}

export interface SampleInfo {
  name: string;
  title: string;
  description: string;
  default_file: string;
  files: string[];
}

export interface LogRecord {
  id: number;
  source_id: string;
  line_no: number;
  timestamp: string | null;
  level: Level;
  service: string;
  host: string | null;
  request_id: string | null;
  route_id: string | null;
  endpoint: string | null;
  http_status: number | null;
  latency_ms: number | null;
  exception_type: string | null;
  message: string;
}

export interface LogRecordFull extends LogRecord {
  environment: string | null;
  trace_id: string | null;
  normalized_message: string;
  stack_trace: string | null;
  raw_line: string;
  extra: Record<string, unknown>;
}

export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

export interface SourceDetail {
  source: Source;
  quality: Quality;
  filters: { services: string[]; levels: Level[] };
}

export interface AnalysisParams {
  similarity_threshold: number;
  gap_minutes: number;
  min_errors: number;
  merge_across_services: boolean;
}

export interface Analysis {
  id: string;
  source_id: string;
  source_name?: string;
  params: AnalysisParams & Record<string, unknown>;
  stats: { incident_count: number; group_count: number; error_records?: number; duration_seconds?: number } & Record<string, unknown>;
  created_at: string;
}

export interface Pattern {
  group_key: string;
  group_id: string;
  title: string;
  template: string;
  count: number;
  services: string[];
  method: string;
}

export interface Incident {
  id: string;
  analysis_id: string;
  number: number;
  label: string;
  title: string;
  severity: Severity;
  status: Status;
  reviewed: boolean;
  first_seen: string | null;
  last_seen: string | null;
  record_count: number;
  error_count: number;
  services: string[];
  top_patterns: Pattern[];
  updated_at: string;
}

export interface TimelineEvent {
  time: string;
  kind: string;
  title: string;
  detail: string;
  origin: "observed" | "inferred";
  evidence_ids: number[];
}

export interface ErrorGroup {
  id: string;
  analysis_id: string;
  title: string;
  template: string;
  services: string[];
  exception_types: string[];
  method: string;
  explanation: string;
  record_count: number;
  first_seen: string | null;
  last_seen: string | null;
  max_level: Level;
  sample_record_ids: number[];
  member_templates?: string[];
}

export interface Note {
  id: number;
  incident_id: string;
  body: string;
  created_at: string;
}

export interface IncidentDetail {
  incident: Incident;
  explanation: string;
  detection: Record<string, unknown>;
  timeline: TimelineEvent[];
  groups: ErrorGroup[];
  representative_records: { pattern_title: string; group_id: string; record: LogRecord }[];
  related_incidents: { id: string; label: string; title: string; severity: Severity; shared_patterns: string[] }[];
  notes: Note[];
  source: Source | null;
  labels: Record<string, string>;
}

export interface RunbookHit {
  rank: number;
  score: number;
  relevance: Strength;
  chunk_id: number;
  document_id: string;
  document_title: string;
  filename: string;
  heading: string;
  citation: string;
  text: string;
  documented_commands: string[];
  origin: "runbook";
}

export interface RetrievalInfo {
  requested_backend: string;
  backend: string;
  fallback: boolean;
  fallback_reason: string | null;
  vector_store: string;
  min_relevance: number;
}

export interface SearchResult {
  query: string;
  results: RunbookHit[];
  no_relevant_source: boolean;
  message: string | null;
  retrieval: RetrievalInfo;
  incident_id?: string;
}

export interface RunbookDoc {
  id: string;
  title: string;
  filename: string;
  kind: "upload" | "sample";
  size_bytes: number;
  chunk_count: number;
  created_at: string;
}

export interface KnowledgeStatus {
  documents: number;
  chunks: number;
  built_at: string | null;
  chunk_size_chars: number;
  chunk_overlap_chars: number;
  retrieval: RetrievalInfo;
}

export interface Fact {
  statement: string;
  evidence_ids: number[];
  origin: "observed";
}

export interface RetrievedPoint {
  citation: string;
  document_id: string;
  chunk_id: number;
  relevance: Strength;
  text: string;
  origin: "runbook";
}

export interface Hypothesis {
  statement: string;
  reasoning: string;
  origin: "rule" | "ai_hypothesis";
  strength: Strength;
  evidence_ids: number[];
  caveat: string;
}

export interface DiagnosticStep {
  id: string;
  title: string;
  instruction: string;
  origin: "runbook" | "rule" | "ai_hypothesis";
  strength: Strength;
  strength_reason: string;
  evidence_ids: number[];
  evidence_match: "specific" | "general";
  citation: string | null;
  expected_observation: string;
  documented_commands: string[];
  read_only: true;
}

export interface NotSuggested {
  text: string;
  reason: string;
  citation: string | null;
  origin: "runbook" | "ai_hypothesis";
}

export interface Summary {
  incident_id: string;
  incident_label: string;
  generated_by: string;
  used_ai: boolean;
  ai_error: string | null;
  ai_available: boolean;
  headline: string;
  ai_narrative: string | null;
  facts: Fact[];
  retrieved: RetrievedPoint[];
  no_relevant_source: boolean;
  hypotheses: Hypothesis[];
  steps: DiagnosticStep[];
  not_suggested: NotSuggested[];
  limitations: string[];
  created_at: string;
  notice: string;
}

export interface Answer {
  question: string;
  answer: string;
  answer_origin: "retrieval" | "ai_hypothesis";
  used_ai: boolean;
  ai_error: string | null;
  evidence: { id: number; timestamp: string | null; level: Level; service: string; message: string }[];
  runbook_sources: { citation: string; relevance: Strength; text: string }[];
  no_relevant_source: boolean;
  uncertainty: string | null;
}

export interface ActivityItem {
  kind: string;
  detail: string;
  incident_id: string | null;
  created_at: string;
}

export interface Dashboard {
  has_data: boolean;
  reason?: string;
  source?: Source;
  sources: Source[];
  totals?: { records: number; errors: number; warnings: number; info: number };
  severity_distribution?: { level: Level; count: number }[];
  trend?: { bucket_seconds: number; points: { time: string; errors: number; warnings: number; total: number }[] };
  top_services?: { service: string; errors: number }[];
  analysis?: Analysis | null;
  analysis_needed?: boolean;
  incidents?: {
    total: number;
    critical_or_high: number;
    by_severity: Record<string, number>;
    by_status: Record<string, number>;
    recent: Incident[];
  };
  top_errors?: ErrorGroup[];
  recent_activity?: ActivityItem[];
}

export interface AppSettings {
  version: string;
  ai: {
    provider: string;
    model: string | null;
    key_set: boolean;
    ready: boolean;
    problem: string | null;
    timeout_seconds: number;
    max_evidence_records: number;
  };
  retrieval: { embedding_backend: string; embedding_model: string; chunk_size_chars: number; chunk_overlap_chars: number; min_relevance: number };
  detection_defaults: { similarity_threshold: number; gap_minutes: number; min_errors: number };
  limits: { max_upload_mb: number; max_log_records: number; max_runbook_mb: number };
  privacy: string;
  safety: string;
  how_to_change: string;
}
