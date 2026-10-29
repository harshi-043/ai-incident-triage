import { afterEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Route, Routes } from "react-router-dom";
import { DashboardPage } from "./DashboardPage";
import { IncidentDetailPage } from "./IncidentDetailPage";
import { InvestigationPage } from "./InvestigationPage";
import { KnowledgePage } from "./KnowledgePage";
import { SettingsPage } from "./SettingsPage";
import { analysis, incident, incidentDetail, settingsNoAi, source, summaryNoSource } from "../test/fixtures";
import { mockApi, renderApp } from "../test/render";

afterEach(() => {
  vi.unstubAllGlobals();
  try { window.localStorage.clear(); } catch { /* ignore */ }
});

const base = {
  "GET /api/logs/sources": { items: [source] },
  "GET /api/analyses": { items: [analysis] },
  "GET /api/logs/samples": { items: [], note: "" },
  "GET /api/health": { status: "ok", version: "0.1.0", checks: { database: "ok" }, ai_provider: "none", embedding_backend: "tfidf" },
  "GET /api/settings": settingsNoAi,
};

describe("Dashboard", () => {
  it("invites the user to load logs when nothing is loaded", async () => {
    mockApi({ ...base, "GET /api/logs/sources": { items: [] }, "GET /api/logs/samples": { items: [{ name: "application", title: "Web shop (synthetic)", description: "d", default_file: "a.log", files: ["a.log"] }], note: "" } });
    renderApp(<DashboardPage />);
    expect(await screen.findByText(/start by loading some logs/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /upload a log file/i })).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: /load sample: web shop/i })).toBeInTheDocument();
  });

  it("shows a readable error when the API is down", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => { throw new TypeError("Failed to fetch"); }));
    renderApp(<DashboardPage />);
    expect(await screen.findByText(/cannot reach the api/i)).toBeInTheDocument();
  });
});

describe("Incident detail", () => {
  const routes = (extra = {}) => ({
    ...base,
    "GET /api/incidents/inc1": incidentDetail,
    ...extra,
  });
  const ui = (
    <Routes><Route path="/incidents/:id" element={<IncidentDetailPage />} /></Routes>
  );

  it("shows why the incident was flagged and its timeline", async () => {
    mockApi(routes());
    renderApp(ui, "/incidents/inc1");
    expect(await screen.findByText(/25 errors in 20 minutes on payments/)).toBeInTheDocument();
    expect(screen.getByText("First error")).toBeInTheDocument();
  });

  it("saves a status change through PATCH", async () => {
    const { calls } = mockApi(routes({ "PATCH /api/incidents/inc1": { incident: { ...incident, status: "investigating" } } }));
    renderApp(ui, "/incidents/inc1");
    const select = await screen.findByLabelText(/status/i);
    await userEvent.selectOptions(select, "investigating");
    await waitFor(() => expect(calls.some((c) => c.method === "PATCH" && (c.body as { status?: string }).status === "investigating")).toBe(true));
  });

  it("adds a note", async () => {
    // The page reloads the incident after saving, so the fake API remembers the note like the real one does.
    const note = { id: 1, incident_id: "inc1", body: "Checked the pool size", created_at: "2026-01-01T11:00:00Z" };
    let saved = false;
    const { calls } = mockApi(routes({
      "GET /api/incidents/inc1": () => ({ ...incidentDetail, notes: saved ? [note] : [] }),
      "POST /api/incidents/inc1/notes": () => { saved = true; return { note }; },
    }));
    renderApp(ui, "/incidents/inc1");
    const box = await screen.findByRole("textbox", { name: /note/i });
    await userEvent.type(box, "Checked the pool size");
    await userEvent.click(screen.getByRole("button", { name: /add note/i }));
    await waitFor(() => expect(calls.some((c) => c.method === "POST" && c.path.endsWith("/notes"))).toBe(true));
    expect(await screen.findByText("Checked the pool size")).toBeInTheDocument();
  });
});

describe("AI Investigation", () => {
  const routes = (extra = {}) => ({
    ...base,
    "GET /api/incidents": { items: [incident], total: 1, page: 1, page_size: 200 },
    "GET /api/incidents/inc1/summary": { summary: null },
    ...extra,
  });

  it("says AI is unavailable and still generates a summary without it", async () => {
    const { calls } = mockApi(routes({ "POST /api/incidents/inc1/summarize": { summary: summaryNoSource } }));
    renderApp(<InvestigationPage />, "/investigation");
    expect((await screen.findAllByText(/no ai provider is configured/i)).length).toBeGreaterThan(0);
    const toggle = screen.getByRole("checkbox", { name: /ask an ai provider/i });
    expect(toggle).not.toBeChecked();
    await userEvent.click(await screen.findByRole("button", { name: /generate summary/i }));
    expect(await screen.findByText(/1\. Facts from the logs/)).toBeInTheDocument();
    expect(screen.getByText(/no relevant source was found/i)).toBeInTheDocument();
    expect(screen.getByText(/3\. Hypotheses \(not confirmed\)/)).toBeInTheDocument();
    expect(screen.getByText(/4\. Suggested checks \(read-only\)/)).toBeInTheDocument();
    const sent = calls.find((c) => c.path.endsWith("/summarize"));
    expect(sent?.body).toEqual({ use_ai: false });
  });
});

describe("Knowledge Base", () => {
  const routes = (extra = {}) => ({
    ...base,
    "GET /api/knowledge/status": { documents: 0, chunks: 0, built_at: null, chunk_size_chars: 900, chunk_overlap_chars: 120,
      retrieval: { requested_backend: "sentence-transformers", backend: "tfidf", fallback: true, fallback_reason: "The model could not be loaded.", vector_store: "numpy", min_relevance: 0.16 } },
    "GET /api/knowledge/documents": { items: [] },
    ...extra,
  });

  it("explains an empty knowledge base and the search fallback", async () => {
    mockApi(routes());
    renderApp(<KnowledgePage />, "/knowledge");
    expect(await screen.findByText(/knowledge base is empty/i)).toBeInTheDocument();
    expect(await screen.findByText(/model could not be loaded/i)).toBeInTheDocument();
  });

  it("shows the no-relevant-source message instead of weak matches", async () => {
    mockApi(routes({ "POST /api/knowledge/search": { query: "disk full", results: [], no_relevant_source: true, message: "No relevant source was found in the knowledge base.", retrieval: {} } }));
    renderApp(<KnowledgePage />, "/knowledge");
    await userEvent.type(await screen.findByLabelText(/search the knowledge base/i), "disk full");
    await userEvent.click(screen.getByRole("button", { name: /^search$/i }));
    expect(await screen.findByText(/no relevant source was found/i)).toBeInTheDocument();
  });
});

describe("Settings", () => {
  it("never shows a key value, only whether one is set", async () => {
    mockApi({ ...base, "GET /api/settings": { ...settingsNoAi, ai: { ...settingsNoAi.ai, provider: "anthropic", model: "m", key_set: true, ready: true, problem: null } } });
    renderApp(<SettingsPage />, "/settings");
    expect(await screen.findByText(/set \(hidden\)/i)).toBeInTheDocument();
    expect(screen.queryByRole("textbox")).toBeNull(); // no field to type a key into
  });
});
