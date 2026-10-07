import type { SweepSummary } from "@/lib/api";

// Segments use pathLength=100, so a dash length is a plain percentage of all checks.
export default function ScoreRing({ sum }: { sum: SweepSummary }) {
  const t = sum.total || 1;
  const pct = Math.round((sum.passed / t) * 100);
  const parts = [
    { n: sum.passed, color: "var(--ok)", start: 0 },
    { n: sum.warning, color: "var(--wa)", start: sum.passed },
    { n: sum.failed, color: "var(--fa)", start: sum.passed + sum.warning },
  ];
  return (
    <div role="img" aria-label={`${pct} percent passed`} className="relative size-28 shrink-0">
      <svg viewBox="0 0 100 100" className="size-full" aria-hidden="true">
        <circle cx="50" cy="50" r="40" fill="none" strokeWidth="12" stroke="var(--line)" />
        {parts.map(
          (p) =>
            p.n > 0 && (
              <circle
                key={p.color}
                cx="50"
                cy="50"
                r="40"
                fill="none"
                strokeWidth="12"
                pathLength="100"
                stroke={p.color}
                strokeDasharray={`${(p.n / t) * 100} 100`}
                strokeDashoffset={-(p.start / t) * 100}
                transform="rotate(-90 50 50)"
              />
            ),
        )}
      </svg>
      <span className="absolute inset-0 grid place-items-center font-display text-2xl font-bold">{pct}%</span>
    </div>
  );
}
