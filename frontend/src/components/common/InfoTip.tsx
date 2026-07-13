import { Info } from "lucide-react";

/** Small info icon with a hover/focus tooltip explaining a term. */
export function InfoTip({ text, label = "More info" }: { text: string; label?: string }) {
  return (
    <span className="group relative inline-flex align-middle">
      <button
        type="button"
        aria-label={label}
        className="text-muted-foreground/70 transition-colors hover:text-primary focus:text-primary focus:outline-none"
      >
        <Info className="size-3.5" />
      </button>
      <span
        role="tooltip"
        className="pointer-events-none absolute left-1/2 top-6 z-30 w-60 -translate-x-1/2 rounded-md border border-border bg-card p-2.5 text-xs leading-relaxed text-muted-foreground opacity-0 shadow-xl transition-opacity duration-150 group-hover:opacity-100 group-focus-within:opacity-100"
      >
        {text}
      </span>
    </span>
  );
}
