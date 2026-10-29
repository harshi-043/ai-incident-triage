import { Component, type ReactNode } from "react";

/** Last line of defence: a crash in one page shows a message instead of a blank screen. */
export class ErrorBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  componentDidCatch(error: Error) {
    console.error("Page error:", error);
  }

  render() {
    if (this.state.failed) {
      return (
        <div role="alert" className="mx-auto max-w-lg rounded-xl border border-danger/30 bg-danger-bg p-6 text-center text-danger">
          <h1 className="text-lg font-semibold">Something went wrong on this page</h1>
          <p className="mt-1 text-sm">Reload the page to try again. If it keeps happening, check the browser console and the backend log.</p>
          <button type="button" className="mt-3 rounded-lg bg-ocean-700 px-4 py-2 text-sm text-white" onClick={() => window.location.reload()}>
            Reload
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
