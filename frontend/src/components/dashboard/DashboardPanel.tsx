import { useMutation } from "@tanstack/react-query";
import { BarChart3, Plus, Sparkles, Wand2, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { ChartRenderer } from "@/components/charts/ChartRenderer";
import { Modal } from "@/components/common/Modal";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { EmptyState, Spinner } from "@/components/ui/misc";
import { formatValue } from "@/lib/utils";
import { useDashboard, useSaveDashboard } from "@/hooks/useDatasets";
import { aiService } from "@/services/aiService";
import type { ChartSpec, KpiCard as KpiCardType } from "@/types/models";

interface ExplainState {
  title: string;
  text?: string;
  generatedBy?: string;
}

/** Customizable dashboard: add/remove KPIs and charts; layout persists per user. */
export function DashboardPanel({ datasetId }: { datasetId: number }) {
  const { data, isLoading } = useDashboard(datasetId);
  const save = useSaveDashboard(datasetId);

  const [kpiIds, setKpiIds] = useState<string[]>([]);
  const [chartIds, setChartIds] = useState<string[]>([]);
  const [picker, setPicker] = useState<"kpi" | "chart" | null>(null);
  const [command, setCommand] = useState("");
  // NL-created widgets not yet present in the server pool (until next refetch).
  const [extraKpis, setExtraKpis] = useState<KpiCardType[]>([]);
  const [extraCharts, setExtraCharts] = useState<ChartSpec[]>([]);
  const [explain, setExplain] = useState<ExplainState | null>(null);

  // Seed local selection from the server once it arrives.
  useEffect(() => {
    if (data) {
      setKpiIds(data.selected.kpis);
      setChartIds(data.selected.charts);
    }
  }, [data]);

  const kpiById = useMemo(
    () => new Map([...(data?.pool.kpis ?? []), ...extraKpis].map((k) => [k.id, k])),
    [data, extraKpis]
  );
  const chartById = useMemo(
    () => new Map([...(data?.pool.charts ?? []), ...extraCharts].map((c) => [c.id, c])),
    [data, extraCharts]
  );

  const explainMutation = useMutation({
    mutationFn: (widget: { kind: "kpi"; kpi: KpiCardType } | { kind: "chart"; chart: ChartSpec }) =>
      widget.kind === "kpi"
        ? aiService.explainKpi(datasetId, widget.kpi)
        : aiService.explainChart(datasetId, widget.chart),
    onSuccess: (res) =>
      setExplain((e) => (e ? { ...e, text: res.explanation, generatedBy: res.generated_by } : e)),
    onError: (e: Error) => {
      toast.error(e.message);
      setExplain(null);
    },
  });

  const commandMutation = useMutation({
    mutationFn: (cmd: string) => aiService.chartCommand(datasetId, cmd),
    onSuccess: (res) => {
      if (res.kind === "kpi" && res.kpi) {
        setExtraKpis((k) => [...k.filter((x) => x.id !== res.kpi!.id), res.kpi!]);
        persist([...kpiIds.filter((i) => i !== res.kpi!.id), res.kpi.id], chartIds);
      } else if (res.kind === "chart" && res.chart) {
        setExtraCharts((c) => [...c.filter((x) => x.id !== res.chart!.id), res.chart!]);
        persist(kpiIds, [...chartIds.filter((i) => i !== res.chart!.id), res.chart.id]);
      }
      setCommand("");
      toast.success(res.message);
    },
    onError: (e: Error) => toast.error(e.message),
  });

  if (isLoading) return <Spinner label="Building dashboard…" />;
  if (!data) return null;

  const persist = (kpis: string[], charts: string[]) => {
    setKpiIds(kpis);
    setChartIds(charts);
    save.mutate({ kpis, charts });
  };

  const addKpi = (id: string) => persist([...kpiIds, id], chartIds);
  const removeKpi = (id: string) => persist(kpiIds.filter((k) => k !== id), chartIds);
  const addChart = (id: string) => persist(kpiIds, [...chartIds, id]);
  const removeChart = (id: string) => persist(kpiIds, chartIds.filter((c) => c !== id));

  const explainKpi = (kpi: KpiCardType) => {
    setExplain({ title: kpi.label });
    explainMutation.mutate({ kind: "kpi", kpi });
  };
  const explainChart = (chart: ChartSpec) => {
    setExplain({ title: chart.title });
    explainMutation.mutate({ kind: "chart", chart });
  };

  const selectedKpis = kpiIds.map((id) => kpiById.get(id)).filter(Boolean) as KpiCardType[];
  const selectedCharts = chartIds.map((id) => chartById.get(id)).filter(Boolean) as ChartSpec[];
  const availableKpis = data.pool.kpis.filter((k) => !kpiIds.includes(k.id));
  const availableCharts = data.pool.charts.filter((c) => !chartIds.includes(c.id));

  return (
    <div className="space-y-4">
      {/* NL chart-on-command */}
      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (command.trim()) commandMutation.mutate(command.trim());
        }}
        className="flex gap-2 rounded-xl border border-primary/30 bg-primary/5 p-3"
      >
        <div className="flex items-center gap-2 pl-1 text-sm font-medium text-primary">
          <Wand2 className="size-4" />
        </div>
        <Input
          placeholder='Describe a widget… e.g. "average price by region" or "trend of sales over time"'
          value={command}
          onChange={(e) => setCommand(e.target.value)}
          className="border-0 bg-transparent focus-visible:ring-0"
        />
        <Button type="submit" variant="gradient" size="sm" disabled={commandMutation.isPending || !command.trim()}>
          <Sparkles className="size-4" /> {commandMutation.isPending ? "Creating…" : "Create with AI"}
        </Button>
      </form>

      {/* KPI row */}
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-muted-foreground">KPIs</h3>
        <Button variant="outline" size="sm" onClick={() => setPicker("kpi")} disabled={!availableKpis.length}>
          <Plus className="size-4" /> Add KPI
        </Button>
      </div>
      {selectedKpis.length === 0 ? (
        <EmptyState icon={<BarChart3 className="size-6" />} title="No KPIs" description="Add KPIs to your dashboard." />
      ) : (
        <div className="card-grid">
          {selectedKpis.map((kpi) => (
            <Card key={kpi.id} className="group relative p-5">
              <div className="absolute right-2 top-2 flex gap-1 opacity-0 transition-opacity group-hover:opacity-100">
                <button
                  onClick={() => explainKpi(kpi)}
                  className="rounded-md p-1 text-muted-foreground hover:text-primary"
                  title="Explain this (AI)"
                >
                  <Sparkles className="size-4" />
                </button>
                <button
                  onClick={() => removeKpi(kpi.id)}
                  className="rounded-md p-1 text-muted-foreground hover:text-destructive"
                  title="Remove"
                >
                  <X className="size-4" />
                </button>
              </div>
              <p className="text-sm text-muted-foreground">{kpi.label}</p>
              <p className="mt-2 text-2xl font-bold tracking-tight">{formatValue(kpi.value, kpi.format)}</p>
            </Card>
          ))}
        </div>
      )}

      {/* Charts */}
      <div className="flex items-center justify-between pt-2">
        <h3 className="text-sm font-semibold text-muted-foreground">Charts</h3>
        <Button variant="outline" size="sm" onClick={() => setPicker("chart")} disabled={!availableCharts.length}>
          <Plus className="size-4" /> Add chart
        </Button>
      </div>
      {selectedCharts.length === 0 ? (
        <EmptyState icon={<BarChart3 className="size-6" />} title="No charts" description="Add charts to build your view." />
      ) : (
        <div className="grid gap-4 lg:grid-cols-2">
          {selectedCharts.map((chart) => (
            <Card key={chart.id} className="group relative">
              <div className="flex items-center justify-between p-5 pb-0">
                <CardTitle>{chart.title}</CardTitle>
                <div className="flex gap-1 opacity-0 transition-opacity group-hover:opacity-100">
                  <button
                    onClick={() => explainChart(chart)}
                    className="rounded-md p-1 text-muted-foreground hover:text-primary"
                    title="Explain this (AI)"
                  >
                    <Sparkles className="size-4" />
                  </button>
                  <button
                    onClick={() => removeChart(chart.id)}
                    className="rounded-md p-1 text-muted-foreground hover:text-destructive"
                    title="Remove"
                  >
                    <X className="size-4" />
                  </button>
                </div>
              </div>
              <CardContent className="pt-3">
                <ChartRenderer spec={chart} />
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* AI explanation */}
      <Modal
        open={!!explain}
        onClose={() => setExplain(null)}
        title={explain?.title ?? ""}
        description="AI explanation in plain business terms"
      >
        {explain?.text ? (
          <div className="space-y-3">
            <p className="text-sm leading-relaxed">{explain.text}</p>
            <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
              <Sparkles className="size-3 text-accent" />
              {explain.generatedBy === "ai" ? "Generated by DataPilot AI" : "Deterministic summary (AI offline)"}
            </p>
          </div>
        ) : (
          <Spinner label="Asking DataPilot AI…" />
        )}
      </Modal>

      {/* Add-KPI picker */}
      <Modal open={picker === "kpi"} onClose={() => setPicker(null)} title="Add a KPI" description="Pick from metrics computed for your data.">
        {availableKpis.length === 0 ? (
          <p className="text-sm text-muted-foreground">All available KPIs are already on your dashboard.</p>
        ) : (
          <div className="grid gap-2 sm:grid-cols-2">
            {availableKpis.map((kpi) => (
              <button
                key={kpi.id}
                onClick={() => {
                  addKpi(kpi.id);
                  setPicker(null);
                }}
                className="flex items-center justify-between rounded-lg border border-border bg-background p-3 text-left transition-colors hover:border-primary/50"
              >
                <div>
                  <p className="text-sm font-medium">{kpi.label}</p>
                  <p className="text-xs text-muted-foreground">{formatValue(kpi.value, kpi.format)}</p>
                </div>
                <Plus className="size-4 text-primary" />
              </button>
            ))}
          </div>
        )}
      </Modal>

      {/* Add-chart picker */}
      <Modal open={picker === "chart"} onClose={() => setPicker(null)} wide title="Add a chart" description="Pick a chart to add to your dashboard.">
        {availableCharts.length === 0 ? (
          <p className="text-sm text-muted-foreground">All available charts are already on your dashboard.</p>
        ) : (
          <div className="grid gap-3 sm:grid-cols-2">
            {availableCharts.map((chart) => (
              <button
                key={chart.id}
                onClick={() => {
                  addChart(chart.id);
                  setPicker(null);
                }}
                className="rounded-lg border border-border bg-background p-3 text-left transition-colors hover:border-primary/50"
              >
                <div className="mb-2 flex items-center justify-between">
                  <span className="text-sm font-medium">{chart.title}</span>
                  <span className="rounded-full bg-secondary px-2 py-0.5 text-xs uppercase text-muted-foreground">
                    {chart.type}
                  </span>
                </div>
                <ChartRenderer spec={chart} height={140} />
              </button>
            ))}
          </div>
        )}
      </Modal>
    </div>
  );
}
