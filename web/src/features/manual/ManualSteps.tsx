"use client";

import { useState } from "react";
import { getManual, type ManualSummary, type RunSteps } from "@/lib/api";
import { errMsg } from "./useRunSession";

type Preview = { state: "idle" | "loading" } | { state: "ok"; text: string } | { state: "error"; message: string };

// Collapsible, quiet view of the parsed manual (replaces the old prominent cards).
export default function ManualSteps({ data, manual }: { data: RunSteps; manual: ManualSummary | null }) {
  const cases = data.test_cases.filter((tc) => tc.title !== "Menu sweep");
  const rules = data.field_rules ?? [];
  const [preview, setPreview] = useState<Preview>({ state: "idle" });

  async function load() {
    if (!manual) return;
    setPreview({ state: "loading" });
    try {
      setPreview({ state: "ok", text: (await getManual(manual.id)).text });
    } catch (err) {
      setPreview({ state: "error", message: errMsg(err) });
    }
  }

  return (
    <details className="group rounded-xl border border-line bg-panel">
      <summary className="flex cursor-pointer list-none items-center gap-2 rounded-xl px-4 py-3 focus:outline-none focus-visible:ring-2 focus-visible:ring-pri">
        <span aria-hidden="true" className="text-mut transition-transform group-open:rotate-90 motion-reduce:transition-none">
          ▸
        </span>
        <span className="font-display text-base font-semibold">Manual steps</span>
        <span className="text-xs text-mut">
          {cases.length === 0 ? "no test cases found" : `${cases.length} test case${cases.length === 1 ? "" : "s"}`}
        </span>
      </summary>
      <div className="space-y-3 border-t border-line px-4 py-3">
        {cases.length === 0 && <p className="text-mut">No test cases were found in the manual.</p>}
        {cases.map((tc) => (
          <article key={tc.id} aria-labelledby={`tc-${tc.id}`}>
            <h4 id={`tc-${tc.id}`} className="wrap-break-word font-medium">
              {tc.order}. {tc.title}
            </h4>
            <ol className="mt-1 space-y-1">
              {tc.steps.map((st) => (
                <li
                  key={st.id}
                  className={`rounded-md border px-3 py-1.5 ${st.unclear ? "border-wa/50 bg-wa/10" : "border-line"}`}
                >
                  <span className="mr-2 text-mut">{st.order}.</span>
                  <code className="mr-2 rounded bg-panel2 px-1.5 py-0.5 font-mono text-xs">{st.action}</code>
                  <span className="wrap-break-word">{st.target}</span>
                  {st.value && <span className="wrap-break-word text-mut"> = {st.value}</span>}
                  {st.expected && <span className="block wrap-break-word text-xs text-mut">Expected: {st.expected}</span>}
                  {st.unclear && (
                    <span className="block text-xs font-medium text-wa">
                      <span aria-hidden="true">! </span>Unclear: this step will be skipped.
                    </span>
                  )}
                </li>
              ))}
            </ol>
          </article>
        ))}
        <div>
          <h4 className="font-medium">Rules found in the manual</h4>
          {rules.length === 0 ? (
            <p className="mt-1 text-xs text-mut">No field rules were found in this manual.</p>
          ) : (
            <ul className="mt-1 space-y-1">
              {rules.map((r, i) => (
                <li key={i} className="rounded-md border border-line px-3 py-1.5">
                  <span className="wrap-break-word font-medium">{r.field}</span>
                  {r.rule && <span className="wrap-break-word text-mut">: {r.rule}</span>}
                  {r.valid.length > 0 && (
                    <span className="block wrap-break-word font-mono text-xs text-ok">
                      <span aria-hidden="true">✓ </span>Valid: {r.valid.join(" | ")}
                    </span>
                  )}
                  {r.invalid.length > 0 && (
                    <span className="block wrap-break-word font-mono text-xs text-fa">
                      <span aria-hidden="true">✕ </span>Invalid: {r.invalid.join(" | ")}
                    </span>
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>
        {manual && (
          <div>
            <button
              type="button"
              onClick={load}
              disabled={preview.state === "loading"}
              className="rounded-md border border-line bg-panel2 px-2.5 py-1 text-xs font-medium text-ink hover:brightness-110 focus:outline-none focus-visible:ring-2 focus-visible:ring-pri disabled:opacity-60"
            >
              {preview.state === "loading" ? "Loading…" : "Preview stored manual text"}
            </button>
            {preview.state === "error" && (
              <p role="alert" className="mt-2 text-fa">
                {preview.message}
              </p>
            )}
            {preview.state === "ok" && (
              <pre className="mt-2 max-h-72 overflow-auto whitespace-pre-wrap break-words rounded-md bg-panel2 p-3 font-mono text-xs">
                {preview.text}
              </pre>
            )}
          </div>
        )}
      </div>
    </details>
  );
}
