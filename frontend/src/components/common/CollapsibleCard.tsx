import { ChevronDown } from "lucide-react";
import { useState, type ReactNode } from "react";

import { Card, CardContent, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";

interface CollapsibleCardProps {
  title: ReactNode;
  defaultOpen?: boolean;
  children: ReactNode;
}

/** Card whose body expands/collapses when the header is clicked. */
export function CollapsibleCard({ title, defaultOpen = true, children }: CollapsibleCardProps) {
  const [open, setOpen] = useState(defaultOpen);

  return (
    <Card>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex w-full items-center justify-between p-5 text-left transition-colors hover:bg-secondary/30"
      >
        <CardTitle>{title}</CardTitle>
        <ChevronDown className={cn("size-5 shrink-0 text-muted-foreground transition-transform", open && "rotate-180")} />
      </button>
      {open && <CardContent className="pt-0">{children}</CardContent>}
    </Card>
  );
}
