import { cn } from "@/lib/utils";

/** Reusable, scrollable data table for preview and query results. */
export function DataTable({
  columns,
  rows,
  maxHeight = 420,
}: {
  columns: string[];
  rows: Record<string, unknown>[];
  maxHeight?: number;
}) {
  return (
    <div className="overflow-auto rounded-lg border border-border" style={{ maxHeight }}>
      <table className="w-full border-collapse text-sm">
        <thead className="sticky top-0 z-10 bg-secondary">
          <tr>
            {columns.map((c) => (
              <th key={c} className="whitespace-nowrap px-3 py-2 text-left font-semibold text-secondary-foreground">
                {c}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i} className={cn("border-t border-border", i % 2 ? "bg-card" : "bg-background")}>
              {columns.map((c) => (
                <td key={c} className="max-w-[240px] truncate px-3 py-1.5 text-muted-foreground">
                  {formatCell(row[c])}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function formatCell(value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "number") return String(value);
  return String(value);
}
