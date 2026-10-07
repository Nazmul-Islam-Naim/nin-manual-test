export type ChipKey = "pending" | "running" | "passed" | "failed" | "warning";

// Icon + text, so status is never colour-only.
const CHIP: Record<ChipKey, { icon: string; label: string; cls: string }> = {
  pending: { icon: "○", label: "Pending", cls: "border-line bg-panel2 text-mut" },
  running: { icon: "●", label: "Running", cls: "border-run/40 bg-run/10 text-run" },
  passed: { icon: "✓", label: "Passed", cls: "border-ok/40 bg-ok/10 text-ok" },
  failed: { icon: "✕", label: "Failed", cls: "border-fa/40 bg-fa/10 text-fa" },
  warning: { icon: "!", label: "Warning", cls: "border-wa/40 bg-wa/10 text-wa" },
};

export default function StatusChip({ k }: { k: ChipKey }) {
  const c = CHIP[k];
  return (
    <span
      className={`inline-flex w-24 shrink-0 items-center justify-center gap-1.5 rounded-full border py-0.5 text-xs font-semibold ${c.cls}`}
    >
      <span aria-hidden="true" className={k === "running" ? "animate-pulse motion-reduce:animate-none" : ""}>
        {c.icon}
      </span>
      {c.label}
    </span>
  );
}
