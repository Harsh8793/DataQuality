import { useMutation } from "@tanstack/react-query";
import { Download, FileText, Table2 } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useDataset } from "@/hooks/useDatasets";
import { datasetService } from "@/services/datasetService";
import { reportService } from "@/services/reportService";

const TYPES = [
  { type: "pdf", label: "PDF Report", icon: FileText, desc: "Executive quality summary" },
] as const;

/** Generate and download reports in multiple formats. */
export function ReportsPanel({ datasetId }: { datasetId: number }) {
  const { data: ds } = useDataset(datasetId);

  const generate = useMutation({
    mutationFn: (type: string) => reportService.generate(datasetId, type),
    onSuccess: async (report) => {
      toast.success(`${report.report_type.toUpperCase()} report generated.`);
      await reportService.download(report.id, `${report.title}.${report.report_type}`);
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const exportCsv = useMutation({
    mutationFn: () => datasetService.exportCsv(datasetId),
    onSuccess: () => toast.success("Dataset exported."),
    onError: (e: Error) => toast.error(e.message),
  });

  return (
    <div className="grid gap-4 sm:grid-cols-2">
      {TYPES.map(({ type, label, icon: Icon, desc }) => (
        <Card key={type}>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Icon className="size-4 text-primary" /> {label}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="mb-4 text-sm text-muted-foreground">{desc}</p>
            <Button
              variant="outline"
              onClick={() => generate.mutate(type)}
              disabled={generate.isPending}
            >
              <Download className="size-4" /> Generate &amp; download
            </Button>
          </CardContent>
        </Card>
      ))}

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Table2 className="size-4 text-primary" /> Dataset (CSV)
          </CardTitle>
        </CardHeader>
        <CardContent>
          <p className="mb-4 text-sm text-muted-foreground">
            {ds?.is_cleaned
              ? "The cleaned data, including any edits and fixes you applied."
              : "The current data, including any edits and fixes you applied."}
          </p>
          <Button variant="outline" onClick={() => exportCsv.mutate()} disabled={exportCsv.isPending}>
            <Download className="size-4" /> {exportCsv.isPending ? "Exporting…" : "Download CSV"}
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
