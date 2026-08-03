import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Label,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { TooltipProps } from "recharts";

import type { ChartSpec } from "@/types/models";

// Categorical palette (accessible, distinct in dark mode).
const COLORS = ["#3b82f6", "#8b5cf6", "#06b6d4", "#22c55e", "#f59e0b", "#ef4444", "#ec4899", "#14b8a6"];

const AXIS = { stroke: "hsl(var(--muted-foreground))", fontSize: 11 };

/** Theme-aware tooltip: solid card background so values stay readable in dark mode. */
function ChartTip({ active, payload, label }: TooltipProps<number, string>) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-lg border border-border bg-card px-3 py-2 text-xs shadow-xl">
      {label != null && label !== "" && <p className="mb-1 font-semibold text-foreground">{String(label)}</p>}
      {payload.map((entry, i) => (
        <p key={i} className="flex items-center gap-1.5 text-foreground">
          <span
            className="inline-block size-2 rounded-full"
            style={{ backgroundColor: (entry.payload as { fill?: string })?.fill ?? entry.color ?? COLORS[i % COLORS.length] }}
          />
          <span className="text-muted-foreground">{entry.name}:</span>
          <span className="font-semibold">
            {typeof entry.value === "number" ? entry.value.toLocaleString() : String(entry.value)}
          </span>
        </p>
      ))}
    </div>
  );
}

const AXIS_TITLE = { fill: "hsl(var(--muted-foreground))", fontSize: 11, fontWeight: 500 };

/** Renders any backend-provided chart spec with Recharts.
 *
 * Axis captions come from the spec (`x_label` / `y_label`) because they carry
 * the aggregation — "Total revenue" reads very differently from "Average
 * revenue", and the data keys alone ("value") say neither.
 */
export function ChartRenderer({ spec, height = 260 }: { spec: ChartSpec; height?: number }) {
  const data = spec.data;

  if (!data.length) {
    return <div className="flex h-40 items-center justify-center text-sm text-muted-foreground">No data</div>;
  }

  const xLabel = spec.x_label;
  const yLabel = spec.y_label;
  // Room for the captions only when there is something to show.
  const xPad = xLabel ? 22 : 0;
  const yPad = yLabel ? 14 : 0;

  return (
    <ResponsiveContainer width="100%" height={height}>
      {spec.type === "bar" ? (
        <BarChart data={data} margin={{ top: 8, right: 8, left: yPad - 8, bottom: xPad + 8 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" vertical={false} />
          <XAxis dataKey={spec.x} tick={AXIS} interval={0} angle={-20} textAnchor="end" height={50}>
            {xLabel && <Label value={xLabel} position="insideBottom" offset={-18} style={AXIS_TITLE} />}
          </XAxis>
          <YAxis tick={AXIS}>
            {yLabel && <Label value={yLabel} angle={-90} position="insideLeft" style={AXIS_TITLE} />}
          </YAxis>
          <Tooltip
            content={<ChartTip />}
            cursor={{ fill: "hsl(var(--secondary))", opacity: 0.4 }}
            formatter={(value) => [value, yLabel ?? spec.y]}
          />
          <Bar dataKey={spec.y} name={yLabel ?? spec.y} radius={[4, 4, 0, 0]}>
            {data.map((_, i) => (
              <Cell key={i} fill={COLORS[i % COLORS.length]} />
            ))}
          </Bar>
        </BarChart>
      ) : spec.type === "pie" ? (
        <PieChart>
          <Tooltip content={<ChartTip />} />
          {/* A pie has no axes, so the measure is named in the legend instead. */}
          {yLabel && (
            <Legend
              verticalAlign="bottom"
              height={24}
              payload={[{ value: yLabel, type: "circle", color: COLORS[0] }]}
            />
          )}
          <Pie
            data={data}
            dataKey={spec.y}
            nameKey={spec.x}
            name={yLabel ?? spec.y}
            cx="50%"
            cy="50%"
            outerRadius={85}
            innerRadius={42}
            paddingAngle={2}
          >
            {data.map((_, i) => (
              <Cell key={i} fill={COLORS[i % COLORS.length]} />
            ))}
          </Pie>
        </PieChart>
      ) : spec.type === "line" ? (
        <LineChart data={data} margin={{ top: 8, right: 12, left: yPad - 8, bottom: xPad + 8 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" vertical={false} />
          <XAxis dataKey={spec.x} tick={AXIS}>
            {xLabel && <Label value={xLabel} position="insideBottom" offset={-12} style={AXIS_TITLE} />}
          </XAxis>
          <YAxis tick={AXIS}>
            {yLabel && <Label value={yLabel} angle={-90} position="insideLeft" style={AXIS_TITLE} />}
          </YAxis>
          <Tooltip content={<ChartTip />} />
          <Line
            type="monotone"
            dataKey={spec.y}
            name={yLabel ?? spec.y}
            stroke="#3b82f6"
            strokeWidth={2}
            dot={{ r: 3 }}
          />
        </LineChart>
      ) : (
        <ScatterChart margin={{ top: 8, right: 12, left: yPad - 8, bottom: xPad + 8 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
          <XAxis type="number" dataKey={spec.x} tick={AXIS} name={xLabel ?? spec.x}>
            {xLabel && <Label value={xLabel} position="insideBottom" offset={-12} style={AXIS_TITLE} />}
          </XAxis>
          <YAxis type="number" dataKey={spec.y} tick={AXIS} name={yLabel ?? spec.y}>
            {yLabel && <Label value={yLabel} angle={-90} position="insideLeft" style={AXIS_TITLE} />}
          </YAxis>
          <Tooltip content={<ChartTip />} cursor={{ strokeDasharray: "3 3" }} />
          <Scatter data={data} fill="#8b5cf6" />
        </ScatterChart>
      )}
    </ResponsiveContainer>
  );
}
