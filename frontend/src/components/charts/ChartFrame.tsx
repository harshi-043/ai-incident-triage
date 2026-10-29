import type { ReactNode } from "react";
import { Card, CardHeader } from "../ui/Card";

/** One palette for every chart. Muted tones, and the error colour is the same red used for "critical". */
export const COLORS = {
  ocean: "#1f6f8b",
  error: "#a63a33",
  warning: "#c58a1b",
  info: "#7d8c96",
  critical: "#a63a33",
  high: "#b5560f",
  medium: "#a47a0b",
  low: "#3f7352",
};

/** A card with a title and an accessible text summary for screen readers. */
export function ChartFrame({
  title,
  subtitle,
  summary,
  children,
  height = 260,
  action,
}: {
  title: string;
  subtitle?: ReactNode;
  summary: string;
  children: ReactNode;
  height?: number;
  action?: ReactNode;
}) {
  return (
    <Card>
      <CardHeader title={title} subtitle={subtitle} action={action} />
      <div role="img" aria-label={`${title}. ${summary}`} style={{ height }} className="w-full">
        {children}
      </div>
    </Card>
  );
}

export const tooltipStyle = {
  contentStyle: { background: "#ffffff", border: "1px solid #dce2df", borderRadius: 8, fontSize: 12 },
  labelStyle: { color: "#1e2a30", fontWeight: 600 },
};
