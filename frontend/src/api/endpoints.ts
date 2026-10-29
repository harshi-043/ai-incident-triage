// One function per backend endpoint. Pages never build URLs by hand.
import { deleteRequest, downloadFile, getJson, patchJson, postJson, uploadFile, type Query } from "./client";
import type {
  Analysis, AnalysisParams, Answer, AppSettings, Dashboard, ErrorGroup, Health, IncidentDetail, Incident, IngestResult, KnowledgeStatus,
  LogRecord, LogRecordFull, Note, Page, RunbookDoc, SampleInfo, SearchResult, Source, SourceDetail, Summary,
} from "./types";

export interface LogQuery {
  source_id: string;
  q?: string;
  level?: string[];
  service?: string[];
  sort?: string;
  order?: "asc" | "desc";
  page?: number;
  page_size?: number;
}

export interface IncidentQuery {
  source_id?: string;
  analysis_id?: string;
  severity?: string[];
  status?: string[];
  reviewed?: boolean;
  q?: string;
  service?: string;
  sort?: string;
  order?: "asc" | "desc";
  page?: number;
  page_size?: number;
}

export type ExportFormat = "md" | "json" | "csv";

export const api = {
  health: (signal?: AbortSignal) => getJson<Health>("/health", undefined, signal),
  settings: (signal?: AbortSignal) => getJson<AppSettings>("/settings", undefined, signal),

  // log sources
  sources: (signal?: AbortSignal) => getJson<{ items: Source[] }>("/logs/sources", undefined, signal),
  sourceDetail: (id: string, signal?: AbortSignal) => getJson<SourceDetail>(`/logs/sources/${id}`, undefined, signal),
  samples: (signal?: AbortSignal) => getJson<{ items: SampleInfo[]; note: string }>("/logs/samples", undefined, signal),
  loadSample: (name: string, file?: string) => postJson<IngestResult>("/logs/samples", { name, file }),
  uploadLog: (file: File) => uploadFile<IngestResult>("/logs/upload", file),
  deleteSource: (id: string) => deleteRequest(`/logs/sources/${id}`),
  logs: (query: LogQuery, signal?: AbortSignal) => getJson<Page<LogRecord>>("/logs", query as unknown as Query, signal),
  logDetail: (id: number, context = 5, signal?: AbortSignal) =>
    getJson<{ record: LogRecordFull; context: { before: LogRecord[]; after: LogRecord[] } }>(`/logs/${id}`, { context }, signal),

  // analysis
  analyze: (sourceId: string, params: Partial<AnalysisParams> & { force_new?: boolean } = {}) =>
    postJson<{ analysis: Analysis; reused: boolean }>("/logs/analyze", { source_id: sourceId, ...params }),
  analyses: (sourceId: string, signal?: AbortSignal) => getJson<{ items: Analysis[] }>("/analyses", { source_id: sourceId }, signal),
  groups: (analysisId: string, query: Query = {}, signal?: AbortSignal) =>
    getJson<Page<ErrorGroup>>(`/analyses/${analysisId}/groups`, query, signal),
  dashboard: (sourceId?: string, signal?: AbortSignal) => getJson<Dashboard>("/dashboard/summary", { source_id: sourceId }, signal),

  // incidents
  incidents: (query: IncidentQuery, signal?: AbortSignal) => getJson<Page<Incident>>("/incidents", query as unknown as Query, signal),
  incident: (id: string, signal?: AbortSignal) => getJson<IncidentDetail>(`/incidents/${id}`, undefined, signal),
  incidentRecords: (id: string, query: Query = {}, signal?: AbortSignal) => getJson<Page<LogRecord>>(`/incidents/${id}/records`, query, signal),
  updateIncident: (id: string, body: { status?: string; reviewed?: boolean }) => patchJson<{ incident: Incident }>(`/incidents/${id}`, body),
  addNote: (id: string, body: string) => postJson<{ note: Note }>(`/incidents/${id}/notes`, { body }),
  deleteNote: (id: string, noteId: number) => deleteRequest(`/incidents/${id}/notes/${noteId}`),
  incidentRunbooks: (id: string, signal?: AbortSignal) => getJson<SearchResult>(`/incidents/${id}/runbooks`, undefined, signal),
  summarize: (id: string, useAi: boolean) => postJson<{ summary: Summary }>(`/incidents/${id}/summarize`, { use_ai: useAi }),
  summary: (id: string, signal?: AbortSignal) => getJson<{ summary: Summary | null }>(`/incidents/${id}/summary`, undefined, signal),
  ask: (id: string, question: string, useAi: boolean) => postJson<Answer>(`/incidents/${id}/ask`, { question, use_ai: useAi }),

  // knowledge base
  knowledgeStatus: (signal?: AbortSignal) => getJson<KnowledgeStatus>("/knowledge/status", undefined, signal),
  documents: (signal?: AbortSignal) => getJson<{ items: RunbookDoc[] }>("/knowledge/documents", undefined, signal),
  document: (id: string, signal?: AbortSignal) =>
    getJson<{ document: RunbookDoc; text: string; chunks: { id: number; ordinal: number; heading: string; text: string }[] }>(`/knowledge/documents/${id}`, undefined, signal),
  uploadRunbook: (file: File) => uploadFile<{ document: RunbookDoc; created: boolean }>("/knowledge/documents/upload", file),
  loadSampleRunbooks: () => postJson<{ items: RunbookDoc[]; created: number; note: string }>("/knowledge/samples"),
  deleteDocument: (id: string) => deleteRequest(`/knowledge/documents/${id}`),
  searchRunbooks: (query: string, topK = 5) => postJson<SearchResult>("/knowledge/search", { query, top_k: topK }),

  // exports (these download a file)
  exportIncident: (id: string, format: ExportFormat) => downloadFile(`/incidents/${id}/export`, { format }, `incident.${format}`),
  exportReport: (sourceId: string, format: ExportFormat) => downloadFile("/reports/export", { source_id: sourceId, format }, `incident-report.${format}`),
};
