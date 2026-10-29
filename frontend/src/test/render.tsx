import type { ReactElement } from "react";
import { render } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { vi } from "vitest";
import { AppProvider } from "../context/AppContext";
import { RecordViewerProvider } from "../components/RecordViewer";

export type Handler = (url: URL, init: RequestInit) => unknown;
export type Routes = Record<string, Handler | unknown>;

/**
 * Replace fetch with a tiny fake API. Keys look like "GET /api/health" (path only, no query string).
 * A value can be plain JSON or a function that returns JSON. Unknown requests fail the test loudly.
 * Returns the list of calls so tests can check what was sent.
 */
export function mockApi(routes: Routes) {
  const calls: { method: string; path: string; body: unknown }[] = [];
  const fake = vi.fn(async (input: RequestInfo | URL, init: RequestInit = {}) => {
    const url = new URL(String(input), "http://localhost");
    const method = (init.method ?? "GET").toUpperCase();
    const key = `${method} ${url.pathname}`;
    let body: unknown = undefined;
    if (typeof init.body === "string") body = JSON.parse(init.body);
    calls.push({ method, path: url.pathname, body });
    if (!(key in routes)) {
      return new Response(JSON.stringify({ error: { code: "not_mocked", message: `No mock for ${key}` } }), { status: 500 });
    }
    const entry = routes[key];
    const value = typeof entry === "function" ? (entry as Handler)(url, init) : entry;
    if (value instanceof Response) return value;
    return new Response(JSON.stringify(value), { status: 200, headers: { "Content-Type": "application/json" } });
  });
  vi.stubGlobal("fetch", fake);
  return { calls, fake };
}

/** Render a page inside the same providers the real app uses. */
export function renderApp(ui: ReactElement, path = "/") {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AppProvider>
        <RecordViewerProvider>{ui}</RecordViewerProvider>
      </AppProvider>
    </MemoryRouter>,
  );
}
