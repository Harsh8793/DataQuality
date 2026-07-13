import { Loader2 } from "lucide-react";
import type { HTMLAttributes, LabelHTMLAttributes } from "react";

import { cn } from "@/lib/utils";

/** Loading skeleton block. */
export function Skeleton({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("animate-pulse rounded-md bg-secondary/60", className)} {...props} />;
}

/** Centered spinner with optional label. */
export function Spinner({ label }: { label?: string }) {
  return (
    <div className="flex items-center justify-center gap-2 py-10 text-muted-foreground">
      <Loader2 className="size-5 animate-spin" />
      {label && <span className="text-sm">{label}</span>}
    </div>
  );
}

/** Form field label. */
export function Label({ className, ...props }: LabelHTMLAttributes<HTMLLabelElement>) {
  return <label className={cn("text-sm font-medium text-foreground", className)} {...props} />;
}

/** Simple progress bar (value 0-100). Optional solid indicator color. */
export function Progress({
  value,
  className,
  indicatorColor,
}: {
  value: number;
  className?: string;
  indicatorColor?: string;
}) {
  return (
    <div className={cn("h-2 w-full overflow-hidden rounded-full bg-secondary", className)}>
      <div
        className={cn(
          "h-full rounded-full transition-all duration-500",
          !indicatorColor && "bg-gradient-to-r from-primary to-accent"
        )}
        style={{
          width: `${Math.max(0, Math.min(100, value))}%`,
          ...(indicatorColor ? { backgroundColor: indicatorColor } : {}),
        }}
      />
    </div>
  );
}

/** Empty / error state with optional retry. */
export function EmptyState({
  icon,
  title,
  description,
  action,
}: {
  icon?: React.ReactNode;
  title: string;
  description?: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 rounded-lg border border-dashed border-border py-16 text-center">
      {icon && <div className="text-muted-foreground">{icon}</div>}
      <div>
        <p className="font-medium">{title}</p>
        {description && <p className="mt-1 text-sm text-muted-foreground">{description}</p>}
      </div>
      {action}
    </div>
  );
}
