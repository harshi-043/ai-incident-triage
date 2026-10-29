import { Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { formatNumber } from "../../lib/format";
import { COLORS, tooltipStyle } from "./ChartFrame";

/** Errors and warnings over time (one point per bucket). */
export function TrendChart({ data, bucketSeconds }: { data: { time: string; errors: number; warnings: number }[]; bucketSeconds: number }) {
  const showDate = bucketSeconds >= 6 * 3600;
  const label = (iso: string) => {
    const d = new Date(iso);
    return showDate
      ? d.toLocaleDateString("en-GB", { day: "2-digit", month: "short", timeZone: "UTC" })
      : d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", hour12: false, timeZone: "UTC" });
  };
  return (
    <ResponsiveContainer width="100%" height="100%">
      <AreaChart data={data} margin={{ top: 8, right: 12, bottom: 4, left: 0 }}>
        <CartesianGrid strokeDasharray="3 3" vertical={false} />
        <XAxis dataKey="time" tickFormatter={label} minTickGap={36} tickMargin={6} />
        <YAxis width={40} allowDecimals={false} />
        <Tooltip {...tooltipStyle} labelFormatter={(v) => `${label(String(v))} UTC`} formatter={(value, name) => [formatNumber(Number(value)), String(name)]} />
        <Legend verticalAlign="top" height={24} />
        <Area type="monotone" dataKey="warnings" name="Warnings" stroke={COLORS.warning} fill={COLORS.warning} fillOpacity={0.18} strokeWidth={1.5} />
        <Area type="monotone" dataKey="errors" name="Errors" stroke={COLORS.error} fill={COLORS.error} fillOpacity={0.25} strokeWidth={2} />
      </AreaChart>
    </ResponsiveContainer>
  );
}

/** Horizontal bars for a list of categories. */
export function HorizontalBars({
  data,
  valueLabel = "Count",
  color = COLORS.ocean,
  labelWidth = 120,
}: {
  data: { name: string; value: number; color?: string }[];
  valueLabel?: string;
  color?: string;
  labelWidth?: number;
}) {
  return (
    <ResponsiveContainer width="100%" height="100%">
      <BarChart data={data} layout="vertical" margin={{ top: 4, right: 16, bottom: 4, left: 0 }}>
        <CartesianGrid strokeDasharray="3 3" horizontal={false} />
        <XAxis type="number" allowDecimals={false} />
        <YAxis type="category" dataKey="name" width={labelWidth} interval={0} />
        <Tooltip {...tooltipStyle} formatter={(value) => [formatNumber(Number(value)), valueLabel]} cursor={{ fill: "#e9f2f5" }} />
        <Bar dataKey="value" radius={[0, 4, 4, 0]}>
          {data.map((d) => (
            <Cell key={d.name} fill={d.color ?? color} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
