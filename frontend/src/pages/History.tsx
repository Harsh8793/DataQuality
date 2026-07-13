import { useQuery } from "@tanstack/react-query";
import { Activity } from "lucide-react";
import { Link } from "react-router-dom";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { EmptyState, Spinner } from "@/components/ui/misc";
import { historyService } from "@/services/chatService";
import { formatDate } from "@/lib/utils";

/** Activity history timeline. */
export function History() {
  const { data, isLoading } = useQuery({ queryKey: ["history"], queryFn: () => historyService.list() });
  const items = data?.items ?? [];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">History</h1>
        <p className="text-muted-foreground">Your analysis and cleaning activity.</p>
      </div>

      {isLoading ? (
        <Spinner label="Loading…" />
      ) : items.length === 0 ? (
        <EmptyState icon={<Activity className="size-8" />} title="No activity yet" description="Analyze a dataset to see history here." />
      ) : (
        <Card>
          <CardContent className="pt-5">
            <div className="space-y-4">
              {items.map((item) => (
                <div key={item.id} className="flex gap-3">
                  <div className="mt-1 flex size-8 shrink-0 items-center justify-center rounded-full bg-primary/10 text-primary">
                    <Activity className="size-4" />
                  </div>
                  <div className="flex-1 border-b border-border pb-4">
                    <div className="flex items-center justify-between">
                      <Badge variant="secondary">{item.action}</Badge>
                      <span className="text-xs text-muted-foreground">{formatDate(item.created_at)}</span>
                    </div>
                    <p className="mt-1 text-sm">{item.summary}</p>
                    <Link to={`/datasets/${item.dataset_id}`} className="text-xs text-primary hover:underline">
                      View dataset →
                    </Link>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
