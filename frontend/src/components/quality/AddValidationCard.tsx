import { useMutation } from "@tanstack/react-query";
import { CheckCircle2, Sparkles, Terminal, Wand2, X } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { DataTable } from "@/components/common/DataTable";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Spinner } from "@/components/ui/misc";
import { aiService } from "@/services/aiService";
import type { QualityReport, Severity, ValidationProposal } from "@/types/models";

/** AI validation builder: describe a rule → AI proposes it → approve to enforce it. */
export function AddValidationCard({
  datasetId,
  onAdded,
}: {
  datasetId: number;
  onAdded: (report: QualityReport) => void;
}) {
  const [open, setOpen] = useState(false);
  const [prompt, setPrompt] = useState("");
  const [proposal, setProposal] = useState<ValidationProposal | null>(null);

  const propose = useMutation({
    mutationFn: () => aiService.proposeValidation(datasetId, prompt.trim()),
    onSuccess: setProposal,
    onError: (e: Error) => toast.error(e.message),
  });

  const add = useMutation({
    mutationFn: () => aiService.addValidation(datasetId, proposal!),
    onSuccess: (res) => {
      onAdded(res.report);
      setProposal(null);
      setPrompt("");
      toast.success(`Validation added — score now ${res.report.overall_score}/100`);
    },
    onError: (e: Error) => toast.error(e.message),
  });

  if (!open) {
    return (
      <Card className="border-accent/30 bg-gradient-to-br from-accent/5 to-primary/5">
        <CardContent className="flex flex-wrap items-center gap-3 pt-5">
          <div className="flex size-8 items-center justify-center rounded-lg bg-accent/15 text-accent">
            <Wand2 className="size-4" />
          </div>
          <div className="min-w-0 flex-1">
            <p className="text-sm font-semibold">Add your own validation with AI</p>
            <p className="text-xs text-muted-foreground">
              Know something specific about this data? Describe a rule in plain English and AI turns it into a check.
            </p>
          </div>
          <Button variant="gradient" size="sm" onClick={() => setOpen(true)}>
            <Sparkles className="size-4" /> New validation
          </Button>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className="border-accent/30">
      <CardContent className="space-y-3 pt-5">
        <div className="flex items-center justify-between">
          <CardTitle className="flex items-center gap-2 text-base">
            <Wand2 className="size-4 text-accent" /> Add validation with AI
          </CardTitle>
          <button onClick={() => { setOpen(false); setProposal(null); }} className="text-muted-foreground hover:text-foreground">
            <X className="size-4" />
          </button>
        </div>

        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (prompt.trim()) propose.mutate();
          }}
          className="flex gap-2"
        >
          <Input
            placeholder='e.g. "flag rows where SALE_PRICE is 0" or "ASSMT_DATE must be before today"'
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
          />
          <Button type="submit" variant="outline" size="sm" disabled={propose.isPending || !prompt.trim()}>
            <Sparkles className="size-4" /> {propose.isPending ? "Thinking…" : "Ask AI"}
          </Button>
        </form>

        {propose.isPending && <Spinner label="Interpreting your rule…" />}

        {proposal && !propose.isPending && (
          <div className="space-y-3 rounded-lg border border-border bg-background p-4">
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-medium">{proposal.name}</span>
              <Badge variant={proposal.severity as Severity}>{proposal.severity}</Badge>
              <Badge variant="secondary" className="capitalize">{proposal.dimension}</Badge>
              <Badge variant="default">
                {proposal.matched_rows.toLocaleString()} of {proposal.total_rows.toLocaleString()} rows flagged
              </Badge>
            </div>
            {proposal.description && <p className="text-sm text-muted-foreground">{proposal.description}</p>}

            <div className="rounded-md bg-secondary/60 p-3">
              <div className="mb-1 flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
                <Terminal className="size-3.5" /> Generated condition
              </div>
              <code className="block overflow-x-auto whitespace-pre text-xs text-primary">{proposal.condition}</code>
            </div>

            {proposal.sample_rows.length > 0 && (
              <div>
                <p className="mb-1 text-xs text-muted-foreground">Sample of the flagged rows:</p>
                <DataTable columns={proposal.sample_columns} rows={proposal.sample_rows} maxHeight={220} />
              </div>
            )}

            <p className="text-xs text-muted-foreground">
              Is this correct? Approve to add it as a validation — it will run on every analysis and count toward the score.
            </p>
            <div className="flex gap-2">
              <Button variant="gradient" size="sm" onClick={() => add.mutate()} disabled={add.isPending}>
                <CheckCircle2 className="size-4" /> {add.isPending ? "Adding…" : "Approve & add"}
              </Button>
              <Button variant="ghost" size="sm" onClick={() => setProposal(null)} disabled={add.isPending}>
                Discard
              </Button>
            </div>
            <p className="text-[11px] text-muted-foreground">
              {proposal.generated_by === "ai" ? "Interpreted by DataPilot AI" : "Interpreted by rule parser (AI offline)"}
            </p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
