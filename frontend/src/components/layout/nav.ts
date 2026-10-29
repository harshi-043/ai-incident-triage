import { BookOpen, FileText, LayoutDashboard, Microscope, ScrollText, Settings, ShieldAlert, type LucideIcon } from "lucide-react";

export interface NavItem {
  to: string;
  label: string;
  icon: LucideIcon;
  end?: boolean;
}

export const NAV_ITEMS: NavItem[] = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard, end: true },
  { to: "/logs", label: "Log Explorer", icon: ScrollText },
  { to: "/incidents", label: "Incidents", icon: ShieldAlert },
  { to: "/investigation", label: "AI Investigation", icon: Microscope },
  { to: "/knowledge", label: "Knowledge Base", icon: BookOpen },
  { to: "/reports", label: "Reports", icon: FileText },
  { to: "/settings", label: "Settings", icon: Settings },
];
