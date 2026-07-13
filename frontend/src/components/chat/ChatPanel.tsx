import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Send, Sparkles, Terminal, Trash2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { ChartRenderer } from "@/components/charts/ChartRenderer";
import { ConfirmDialog } from "@/components/common/ConfirmDialog";
import { DataTable } from "@/components/common/DataTable";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { aiService } from "@/services/aiService";
import { chatService } from "@/services/chatService";
import type { ChatMessage } from "@/types/models";

interface Turn {
  question: string;
  answer?: ChatMessage;
}

/** Chat-with-data panel: NL question → SQL → result table + chart. */
export function ChatPanel({ datasetId }: { datasetId: number }) {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState("");
  const [confirmClear, setConfirmClear] = useState(false);
  const sessionRef = useRef<number | undefined>(undefined);
  // How many server messages the current `turns` state was built from. Lets us
  // re-seed when a fresh (larger) history arrives after the stale cached one.
  const seededCount = useRef(-1);
  const qc = useQueryClient();

  // Restore the previous conversation (persisted in the DB) on first load.
  const history = useQuery({
    queryKey: ["chat", datasetId, "history"],
    queryFn: () => chatService.history(datasetId),
  });

  // Data-aware starter questions, generated from this dataset's own columns.
  const suggestions = useQuery({
    queryKey: ["chat", datasetId, "suggestions"],
    queryFn: () => aiService.chatSuggestions(datasetId),
    staleTime: Infinity,
  });

  const ask = useMutation({
    mutationFn: (q: string) => chatService.ask(datasetId, q, sessionRef.current),
    onSuccess: (res) => {
      sessionRef.current = res.session_id;
      setTurns((t) => [...t.slice(0, -1), { question: t[t.length - 1].question, answer: res }]);
      // Keep the cached history in sync so remounts restore the full conversation.
      qc.invalidateQueries({ queryKey: ["chat", datasetId, "history"] });
    },
    onError: (e: Error) => toast.error(e.message),
  });

  useEffect(() => {
    if (!history.data || ask.isPending) return;
    const messages = history.data.messages;
    // Cached data seeds first; when the fresh fetch lands with more messages,
    // seed again. Never shrink an in-progress local conversation.
    if (messages.length === seededCount.current) return;

    const loaded: Turn[] = [];
    for (const m of messages) {
      if (m.role === "user") {
        loaded.push({ question: m.content });
      } else if (loaded.length) {
        loaded[loaded.length - 1].answer = {
          answer: m.content,
          sql: m.sql ?? "",
          columns: m.columns,
          rows: m.rows,
          row_count: m.rows.length,
          chart_spec: m.chart_spec,
          session_id: history.data.session_id ?? 0,
        };
      }
    }
    setTurns((current) => {
      if (loaded.length < current.length) return current;
      seededCount.current = messages.length;
      if (history.data.session_id != null) sessionRef.current = history.data.session_id;
      return loaded;
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [history.data, ask.isPending]);

  const clear = useMutation({
    mutationFn: () => chatService.clearHistory(datasetId),
    onSuccess: () => {
      setTurns([]);
      sessionRef.current = undefined;
      qc.setQueryData(["chat", datasetId, "history"], { session_id: null, messages: [] });
      setConfirmClear(false);
      toast.success("Chat cleared.");
    },
    onError: (e: Error) => {
      toast.error(e.message);
      setConfirmClear(false);
    },
  });

  const submit = (q: string) => {
    if (!q.trim()) return;
    setTurns((t) => [...t, { question: q }]);
    setInput("");
    ask.mutate(q);
  };

  return (
    <div className="space-y-4">
      {turns.length === 0 && (
        <Card>
          <CardContent className="pt-5">
            <div className="mb-1 flex items-center gap-2 text-sm font-medium">
              <Sparkles className="size-4 text-accent" /> Ask anything about your data
            </div>
            <p className="text-sm text-muted-foreground">
              Ask in plain English — totals, averages, top-N, breakdowns or trends. DataPilot AI writes the
              SQL, runs it, and shows the answer with a chart.
            </p>
            {(suggestions.data?.questions?.length ?? 0) > 0 && (
              <div className="mt-3 flex flex-wrap gap-2">
                {suggestions.data!.questions.map((q) => (
                  <button
                    key={q}
                    onClick={() => submit(q)}
                    className="rounded-full border border-primary/40 bg-primary/5 px-3 py-1 text-xs text-primary transition-colors hover:bg-primary/15"
                  >
                    {q}
                  </button>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {turns.length > 0 && (
        <div className="flex justify-end">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setConfirmClear(true)}
            className="text-muted-foreground hover:text-destructive"
          >
            <Trash2 className="size-4" /> Clear chat
          </Button>
        </div>
      )}

      <div className="space-y-4">
        {turns.map((turn, i) => (
          <div key={i} className="space-y-3">
            <div className="flex justify-end">
              <div className="max-w-[80%] rounded-2xl rounded-tr-sm bg-primary px-4 py-2 text-sm text-primary-foreground">
                {turn.question}
              </div>
            </div>
            {turn.answer ? (
              <Card>
                <CardContent className="space-y-3 pt-5">
                  <p className="whitespace-pre-line text-sm">{turn.answer.answer}</p>
                  {turn.answer.sql && (
                    <div className="rounded-md bg-secondary/60 p-3">
                      <div className="mb-1 flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
                        <Terminal className="size-3.5" /> Generated SQL
                      </div>
                      <code className="block overflow-x-auto whitespace-pre text-xs text-primary">{turn.answer.sql}</code>
                    </div>
                  )}
                  {turn.answer.chart_spec && <ChartRenderer spec={turn.answer.chart_spec} height={220} />}
                  {turn.answer.rows.length > 0 && (
                    <DataTable columns={turn.answer.columns} rows={turn.answer.rows} maxHeight={280} />
                  )}
                </CardContent>
              </Card>
            ) : (
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <Sparkles className="size-4 animate-pulse text-accent" /> Thinking…
              </div>
            )}
          </div>
        ))}
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          submit(input);
        }}
        className="sticky bottom-0 flex gap-2 bg-background pt-2"
      >
        <Input placeholder="Ask a question about your data…" value={input} onChange={(e) => setInput(e.target.value)} />
        <Button type="submit" variant="gradient" disabled={ask.isPending}>
          <Send className="size-4" />
        </Button>
      </form>

      <ConfirmDialog
        open={confirmClear}
        destructive
        title="Clear this chat?"
        description="This permanently deletes the conversation history for this dataset."
        confirmLabel="Clear chat"
        loading={clear.isPending}
        onConfirm={() => clear.mutate()}
        onCancel={() => setConfirmClear(false)}
      />
    </div>
  );
}
