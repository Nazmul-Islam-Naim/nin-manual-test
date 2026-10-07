"use client";

import { useState } from "react";
import type { Step } from "@/lib/api";
import ResultRow from "./ResultRow";
import { countOf, type FieldGroup, type FormGroup } from "./model";

function Counts({ steps }: { steps: Step[] }) {
  const c = countOf(steps);
  const chip = (n: number, icon: string, label: string, cls: string) =>
    n > 0 && (
      <span className={`inline-flex items-center gap-1 font-mono text-xs ${cls}`}>
        <span aria-hidden="true">{icon}</span>
        {n}
        <span className="sr-only"> {label}</span>
      </span>
    );
  return (
    <span className="flex shrink-0 items-center gap-2.5">
      {chip(c.failed, "✕", "failed", "text-fa")}
      {chip(c.warning, "!", "warning", "text-wa")}
      {chip(c.passed, "✓", "passed", "text-ok")}
      {chip(c.other, "○", "pending", "text-mut")}
    </span>
  );
}

// Open by default only when something needs attention (or a filter is active); the user's click wins afterwards.
function Collapsible({
  steps,
  forceOpen,
  head,
  className,
  children,
}: {
  steps: Step[];
  forceOpen: boolean;
  head: React.ReactNode;
  className: string;
  children: React.ReactNode;
}) {
  const [user, setUser] = useState<boolean | null>(null);
  const c = countOf(steps);
  const open = user ?? (forceOpen || c.failed + c.warning > 0);
  return (
    <div>
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setUser(!open)}
        className={`flex w-full items-center gap-2 text-left hover:bg-panel2 focus:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-pri ${className}`}
      >
        <span aria-hidden="true" className="text-mut">
          {open ? "▾" : "▸"}
        </span>
        <span className="min-w-0 flex-1 wrap-break-word">{head}</span>
        <Counts steps={steps} />
      </button>
      {open && children}
    </div>
  );
}

function Field({ g, forceOpen }: { g: FieldGroup; forceOpen: boolean }) {
  return (
    <Collapsible
      steps={g.cases}
      forceOpen={forceOpen}
      className="px-4 py-2 text-sm"
      head={
        <>
          <span className="text-mut">Field </span>
          <span className="font-medium">{g.field}</span>
        </>
      }
    >
      <ul className="divide-y divide-line border-t border-line bg-bg/30">
        {g.cases.map((st) => (
          <li key={st.id}>
            <ResultRow st={st} form kase />
          </li>
        ))}
      </ul>
    </Collapsible>
  );
}

export default function FormCases({ g, forceOpen, via }: { g: FormGroup; forceOpen: boolean; via?: string }) {
  return (
    <Collapsible
      steps={g.steps}
      forceOpen={forceOpen}
      className="px-4 py-2.5 font-medium"
      head={
        <>
          <span aria-hidden="true" className="mr-1.5 text-mut">
            ▤
          </span>
          <span className="text-mut">Form </span>
          {g.form}
          {via && <span className="ml-2 text-xs font-normal text-mut">opened by {via}</span>}
          <span className="ml-2 text-xs font-normal text-mut">{g.steps.length} cases</span>
        </>
      }
    >
      <ul className="ml-3 divide-y divide-line border-t border-l border-line sm:ml-6">
        {g.fields.map((f) => (
          <li key={f.field}>
            <Field g={f} forceOpen={forceOpen} />
          </li>
        ))}
      </ul>
    </Collapsible>
  );
}
