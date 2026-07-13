import { cn } from "@/lib/utils";

/** Circular quality-score gauge (0-100) with color by band. */
export function ScoreGauge({ score, size = 160 }: { score: number; size?: number }) {
  const radius = (size - 16) / 2;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference - (Math.max(0, Math.min(100, score)) / 100) * circumference;

  const band =
    score >= 85 ? { color: "hsl(var(--success))", label: "Excellent" }
    : score >= 70 ? { color: "hsl(var(--primary))", label: "Good" }
    : score >= 50 ? { color: "hsl(var(--warning))", label: "Fair" }
    : { color: "hsl(var(--destructive))", label: "Poor" };

  return (
    <div className="relative flex items-center justify-center" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90">
        <circle cx={size / 2} cy={size / 2} r={radius} fill="none" stroke="hsl(var(--secondary))" strokeWidth={10} />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke={band.color}
          strokeWidth={10}
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          style={{ transition: "stroke-dashoffset 0.8s ease-out" }}
        />
      </svg>
      <div className="absolute flex flex-col items-center">
        <span className="text-3xl font-bold">{score.toFixed(0)}</span>
        <span className={cn("text-xs font-medium")} style={{ color: band.color }}>
          {band.label}
        </span>
      </div>
    </div>
  );
}
