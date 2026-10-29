import { lazy, Suspense } from "react";
import { Link, Route, Routes } from "react-router-dom";
import { AppProvider } from "./context/AppContext";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { Layout } from "./components/layout/Layout";
import { EmptyState, LoadingState } from "./components/ui/States";

// Each page is loaded when first opened, which keeps the first download small.
const DashboardPage = lazy(() => import("./pages/DashboardPage").then((m) => ({ default: m.DashboardPage })));
const LogExplorerPage = lazy(() => import("./pages/LogExplorerPage").then((m) => ({ default: m.LogExplorerPage })));
const IncidentsPage = lazy(() => import("./pages/IncidentsPage").then((m) => ({ default: m.IncidentsPage })));
const IncidentDetailPage = lazy(() => import("./pages/IncidentDetailPage").then((m) => ({ default: m.IncidentDetailPage })));
const InvestigationPage = lazy(() => import("./pages/InvestigationPage").then((m) => ({ default: m.InvestigationPage })));
const KnowledgePage = lazy(() => import("./pages/KnowledgePage").then((m) => ({ default: m.KnowledgePage })));
const ReportsPage = lazy(() => import("./pages/ReportsPage").then((m) => ({ default: m.ReportsPage })));
const SettingsPage = lazy(() => import("./pages/SettingsPage").then((m) => ({ default: m.SettingsPage })));

function NotFound() {
  return (
    <EmptyState title="Page not found" action={<Link to="/" className="text-sm font-medium text-ocean-700 underline">Go to the dashboard</Link>}>
      That address does not match any page.
    </EmptyState>
  );
}

export default function App() {
  return (
    <AppProvider>
      <ErrorBoundary>
        <Suspense fallback={<LoadingState label="Loading page..." />}>
          <Routes>
            <Route element={<Layout />}>
              <Route index element={<DashboardPage />} />
              <Route path="logs" element={<LogExplorerPage />} />
              <Route path="incidents" element={<IncidentsPage />} />
              <Route path="incidents/:id" element={<IncidentDetailPage />} />
              <Route path="investigation" element={<InvestigationPage />} />
              <Route path="knowledge" element={<KnowledgePage />} />
              <Route path="reports" element={<ReportsPage />} />
              <Route path="settings" element={<SettingsPage />} />
              <Route path="*" element={<NotFound />} />
            </Route>
          </Routes>
        </Suspense>
      </ErrorBoundary>
    </AppProvider>
  );
}
