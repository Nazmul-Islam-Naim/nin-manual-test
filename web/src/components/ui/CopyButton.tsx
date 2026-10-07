"use client";

import { useState } from "react";

export default function CopyButton({ getText, label = "Copy details", disabled, className }: { getText: () => string; label?: string; disabled?: boolean; className?: string }) {
  const [state, setState] = useState<"idle" | "ok" | "fail">("idle");
  async function copy() {
    try {
      await navigator.clipboard.writeText(getText());
      setState("ok");
    } catch {
      setState("fail");
    }
    setTimeout(() => setState("idle"), 2500);
  }
  return (
    <span className="inline-flex items-center gap-2">
      <button
        type="button"
        onClick={copy}
        disabled={disabled}
        className={`border border-line bg-panel2 font-medium text-ink hover:brightness-110 focus:outline-none focus-visible:ring-2 focus-visible:ring-pri disabled:opacity-50 disabled:hover:brightness-100 ${className ?? "rounded-md px-2.5 py-1 text-xs"}`}
      >
        {label}
      </button>
      <span role="status" className="text-xs text-mut">
        {state === "ok" && "Copied"}
        {state === "fail" && "Copy failed. Select the text and copy it manually."}
      </span>
    </span>
  );
}
