import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { api } from "../api/endpoints";
import { errorMessage } from "../api/client";
import type { Analysis, AnalysisParams, Source } from "../api/types";

const STORAGE_KEY = "triage.selectedSource";

// Browser storage can be missing or blocked (private windows), so every use is wrapped.
function readStored(): string | null {
  try {
    return window.localStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
}
function writeStored(value: string | null) {
  try {
    if (value) window.localStorage.setItem(STORAGE_KEY, value);
    else window.localStorage.removeItem(STORAGE_KEY);
  } catch {
    // ignore: remembering the choice is only a convenience
  }
}

interface AppState {
  sources: Source[];
  selected: Source | null;
  analysis: Analysis | null;
  loading: boolean;
  error: string | null;
  /** Reload the source list. Pass an id to select that source afterwards (for example a new upload). */
  refresh: (selectId?: string) => Promise<void>;
  select: (id: string) => void;
  /** Run the grouping and incident detection for the selected source. */
  runAnalysis: (params?: Partial<AnalysisParams> & { force_new?: boolean }) => Promise<Analysis>;
}

const AppContext = createContext<AppState | null>(null);

export function AppProvider({ children }: { children: ReactNode }) {
  const [sources, setSources] = useState<Source[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(readStored);
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async (selectId?: string) => {
    try {
      setError(null);
      const { items } = await api.sources();
      setSources(items);
      setSelectedId((current) => {
        const wanted = selectId ?? current;
        const next = items.find((s) => s.id === wanted)?.id ?? items[0]?.id ?? null; // newest first
        writeStored(next);
        return next;
      });
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  // The latest analysis of the selected source (if there is one).
  useEffect(() => {
    if (!selectedId) {
      setAnalysis(null);
      return;
    }
    const controller = new AbortController();
    api
      .analyses(selectedId, controller.signal)
      .then((res) => setAnalysis(res.items[0] ?? null))
      .catch((err) => {
        if ((err as Error).name !== "AbortError") setAnalysis(null);
      });
    return () => controller.abort();
  }, [selectedId]);

  const select = useCallback((id: string) => {
    setSelectedId(id);
    writeStored(id);
  }, []);

  const runAnalysis = useCallback(
    async (params: Partial<AnalysisParams> & { force_new?: boolean } = {}) => {
      if (!selectedId) throw new Error("Select a log source first.");
      const res = await api.analyze(selectedId, params);
      setAnalysis(res.analysis);
      return res.analysis;
    },
    [selectedId],
  );

  const value = useMemo<AppState>(
    () => ({ sources, selected: sources.find((s) => s.id === selectedId) ?? null, analysis, loading, error, refresh, select, runAnalysis }),
    [sources, selectedId, analysis, loading, error, refresh, select, runAnalysis],
  );
  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
}

export function useApp(): AppState {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error("useApp must be used inside AppProvider");
  return ctx;
}
