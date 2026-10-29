import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { Menu, ShieldCheck, X } from "lucide-react";
import { RecordViewerProvider } from "../RecordViewer";
import { NAV_ITEMS } from "./nav";
import { HealthDot } from "./HealthDot";
import { SourcePicker } from "./SourcePicker";

function Brand() {
  return (
    <div className="flex items-center gap-2.5 px-2">
      <img src="/favicon.svg" alt="" className="h-8 w-8" />
      <div className="leading-tight">
        <p className="text-base font-semibold text-white">Incident Triage</p>
        <p className="text-[11px] text-nav-soft">Log analysis assistant</p>
      </div>
    </div>
  );
}

function NavList({ onNavigate }: { onNavigate?: () => void }) {
  return (
    <nav aria-label="Main" className="mt-6 flex-1 space-y-0.5">
      {NAV_ITEMS.map(({ to, label, icon: Icon, end }) => (
        <NavLink
          key={to}
          to={to}
          end={end}
          onClick={onNavigate}
          className={({ isActive }) =>
            `flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors ${
              isActive ? "bg-white/15 font-medium text-white" : "text-nav-soft hover:bg-white/10 hover:text-white"
            }`
          }
        >
          <Icon className="h-4 w-4 shrink-0" aria-hidden />
          {label}
        </NavLink>
      ))}
    </nav>
  );
}

export function Layout() {
  const [open, setOpen] = useState(false);
  const location = useLocation();

  // Close the mobile menu whenever the page changes.
  useEffect(() => setOpen(false), [location.pathname]);

  return (
    <RecordViewerProvider>
      <div className="flex min-h-full">
        <aside className="sticky top-0 hidden h-screen w-64 shrink-0 flex-col bg-nav p-4 lg:flex">
          <Brand />
          <NavList />
          <HealthDot />
        </aside>

        {open && (
          <div className="fixed inset-0 z-40 lg:hidden" role="dialog" aria-modal="true" aria-label="Menu">
            <div className="absolute inset-0 bg-black/40" onClick={() => setOpen(false)} />
            <aside className="absolute left-0 top-0 flex h-full w-72 max-w-[85vw] flex-col bg-nav p-4">
              <div className="flex items-start justify-between">
                <Brand />
                <button type="button" onClick={() => setOpen(false)} aria-label="Close menu" className="rounded p-1 text-white hover:bg-white/10">
                  <X className="h-5 w-5" aria-hidden />
                </button>
              </div>
              <NavList onNavigate={() => setOpen(false)} />
              <HealthDot />
            </aside>
          </div>
        )}

        <div className="flex min-w-0 flex-1 flex-col">
          <div className="sticky top-0 z-30 flex items-center gap-3 border-b border-line bg-paper/95 px-4 py-2.5 backdrop-blur sm:px-6">
            <button
              type="button"
              onClick={() => setOpen(true)}
              aria-label="Open menu"
              className="rounded-lg border border-line bg-surface p-2 text-ink hover:bg-ocean-50 lg:hidden"
            >
              <Menu className="h-5 w-5" aria-hidden />
            </button>
            <SourcePicker />
          </div>
          <main className="mx-auto w-full max-w-7xl flex-1 px-4 py-5 sm:px-6 sm:py-6">
            <Outlet />
          </main>
          <footer className="flex items-start gap-2 border-t border-line px-4 py-3 text-xs text-muted sm:px-6">
            <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-ocean-600" aria-hidden />
            <p>Suggestions only. This application never runs commands, restarts services or changes any system. Incidents and hypotheses are aids for a person to check, not confirmed causes.</p>
          </footer>
        </div>
      </div>
    </RecordViewerProvider>
  );
}
