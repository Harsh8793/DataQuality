import { AlertCircle, Lightbulb, TrendingUp, Zap } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { Spinner } from "@/components/ui/misc";
import { useInsights } from "@/hooks/useDatasets";

const ICONS: Record<string, React.ReactNode> = {
  trend: <TrendingUp className="size-4" />,
  anomaly: <AlertCircle className="size-4" />,
  risk: <AlertCircle className="size-4" />,
  opportunity: <Zap className="size-4" />,
};

/** AI-generated business insights. */
export function InsightsPanel({ datasetId }: { datasetId: number }) {
  const { data, isLoading } = useInsights(datasetId);

  if (isLoading) return <Spinner label="Generating AI insights…" />;
  if (!data || data.length === 0)
    return <p className="text-sm text-muted-foreground">No insights available.</p>;

  return (
    <div className="grid gap-4 md:grid-cols-2">
      {data.map((insight, i) => (
        <Card key={i}>
          <CardContent className="pt-5">
            <div className="mb-2 flex items-center gap-2">
              <div className="flex size-8 items-center justify-center rounded-lg bg-accent/15 text-accent">
                {ICONS[insight.category] ?? <Lightbulb className="size-4" />}
              </div>
              <span className="font-semibold">{insight.title}</span>
              <Badge variant="secondary" className="ml-auto capitalize">{insight.category}</Badge>
            </div>
            <p className="text-sm text-muted-foreground">{insight.insight}</p>
            <div className="mt-3 flex items-start gap-2 rounded-md bg-primary/10 p-2 text-sm">
              <Zap className="mt-0.5 size-3.5 shrink-0 text-primary" />
              <span className="text-foreground">{insight.action}</span>
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
