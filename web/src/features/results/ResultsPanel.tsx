"use client";

import { useEffect, useState } from "react";
import type { ManualSummary, RunSteps, Step, TestRun } from "@/lib/api";
import CopyButton from "@/components/ui/CopyButton";
import ManualSteps from "@/features/manual/ManualSteps";
import FormCases from "./FormCases";
import IssuesSummary from "./IssuesSummary";
import ResultRow from "./ResultRow";
import ScoreRing from "./ScoreRing";
import { buildMarkdown, fmtClock, isTimeStop, issuesOf, splitForms, sweepGroups, visibleGroups, type ActionGroup, type Filter } from "./model";

type Props = {
  run: TestRun | null;
  data: RunSteps | null;
  manual: ManualSummary | null;
  startedAt: string | null;
  problem: string | null;
  timedOut: boolean;
  canRun: boolean;
  onRunAgain: () => void;
};

const FILTERS: { key: Filter; label: string }[] = [
  { key: "all", label: "All" },
  { key: "failed", label: "Failed" },
  { key: "warning", label: "Warning" },
  { key: "passed", label: "Passed" },
];

function Spinner({ text }: { text: string }) {
  return (
    <p className="flex items-center gap-2">
      <span
        aria-hidden="true"
        className="inline-block size-4 animate-spin rounded-full border-2 border-pri border-t-transparent motion-reduce:animate-none"
      />
      {text}
    </p>
  );
}

function FormList({ forms, forceOpen, via, nested }: { forms: Step[]; forceOpen: boolean; via?: string; nested?: boolean }) {
  const { plain, byForm } = splitForms(forms);
  return (
    <ul className={`divide-y divide-line border-t border-l border-line bg-bg/30 ${nested ? "ml-3 sm:ml-6" : "ml-4 sm:ml-8"}`}>
      {plain.map((f) => (
        <li key={f.id}>
          <ResultRow st={f} form />
        </li>
      ))}
      {byForm.map((g) => (
        <li key={g.form}>
          <FormCases g={g} forceOpen={forceOpen} via={via} />
        </li>
      ))}
    </ul>
  );
}

function PageActions({ actions, forceOpen }: { actions: ActionGroup[]; forceOpen: boolean }) {
  return (
    <div className="ml-4 border-t border-l border-line bg-bg/30 sm:ml-8">
      <h4 className="px-4 pt-2.5 pb-1 text-xs font-semibold uppercase tracking-wide text-mut">Page actions</h4>
      <ul className="divide-y divide-line">
        {actions.map((a) => (
          <li key={a.action.id}>
            <ResultRow st={a.action} action />
            {a.forms.length > 0 && (
              <FormList
                forms={a.forms}
                forceOpen={forceOpen}
                nested
                via={a.action.target.split(" > ").slice(1).join(" > ")}
              />
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}

function downloadMd(name: string, text: string) {
  const url = URL.createObjectURL(new Blob([text], { type: "text/markdown;charset=utf-8" }));
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

// Ticks locally every second; never re-fetches. Stops ticking once finished.
function Elapsed({ start, end, running, limit }: { start: string; end?: string | null; running: boolean; limit?: number | null }) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!running) return;
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, [running]);
  const from = Date.parse(start);
  const to = running ? now : end ? Date.parse(end) : NaN;
  if (Number.isNaN(from) || Number.isNaN(to)) return null;
  return (
    <span className="font-mono text-xs tabular-nums">
      Elapsed {fmtClock(to - from)}
      {limit ? ` / ${String(limit).padStart(2, "0")}:00` : ""}
    </span>
  );
}

const notice = "rounded-lg border px-3 py-2 wrap-break-word";

export default function ResultsPanel({ run, data, manual, startedAt, problem, timedOut, canRun, onRunAgain }: Props) {
  const [filter, setFilter] = useState<Filter>("all");

  if (!run) {
    return (
      <main className="grid min-h-[50vh] place-items-center p-6 lg:min-h-screen">
        <div className="max-w-sm text-center">
          <div aria-hidden="true" className="mx-auto mb-4 font-mono text-4xl text-pri">
            &gt;_
          </div>
          <h2 className="font-display text-2xl font-bold">No test run yet</h2>
          <p className="mt-2 text-mut">
            Add a manual and the website address on the left, then press Start. Results appear here live while the menus
            are tested.
          </p>
        </div>
      </main>
    );
  }

  const groups = sweepGroups(data);
  const sum = data?.summary;
  const hasSweep = !!sum && sum.total > 0;
  const issues = issuesOf(groups);
  const shown = visibleGroups(groups, filter);
  const status = run.status;
  const parsing = status === "created" || status === "parsing";
  const running = status === "running";
  const doneCount = sum ? sum.total - sum.pending : 0;
  const pct = (n: number) => (sum && sum.total ? `${(n / sum.total) * 100}%` : "0%");
  const counts: Record<Filter, number> = sum
    ? { all: sum.total, failed: sum.failed, warning: sum.warning, passed: sum.passed }
    : { all: 0, failed: 0, warning: 0, passed: 0 };
  const exportable = !!sum && sum.failed + sum.warning > 0;
  const md = () => buildMarkdown(run, data, sum!, data?.note);
  const exportMd = () => downloadMd(`test-report-${run.id.slice(0, 8)}-${new Date().toISOString().slice(0, 10)}.md`, md());
  const hint = hasSweep && !exportable ? "Nothing failed or has a warning, so there is nothing to export." : "";
  const exportCls =
    "rounded-full border border-line bg-panel2 px-4 py-2 text-sm font-semibold text-ink hover:brightness-110 focus:outline-none focus-visible:ring-2 focus-visible:ring-pri disabled:opacity-50 disabled:hover:brightness-100";
  const began = run.started_at ?? data?.started_at ?? startedAt;
  const finishedAt = run.finished_at ?? data?.finished_at;
  const host = run.base_url.replace(/^https?:\/\//, "");

  return (
    <main className="mx-auto w-full max-w-4xl space-y-5 p-5 lg:p-8">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div className="min-w-0">
          <h2 className="font-display text-3xl font-bold leading-tight">Menu, form &amp; action test report</h2>
          <p className="mt-1 wrap-break-word text-mut">
            <span className="font-mono text-xs">{host}</span> · run{" "}
            <span className="font-mono text-xs">{run.id.slice(0, 8)}</span> · <span className="capitalize">{status}</span>
            {began && !Number.isNaN(Date.parse(began)) && (
              <> · started {new Date(began).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</>
            )}
            {began && (running || finishedAt) && (
              <>
                {" · "}
                <Elapsed start={began} end={finishedAt} running={running} limit={run.max_minutes ?? data?.max_minutes} />
              </>
            )}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={exportMd}
            disabled={!exportable}
            aria-describedby={hint ? "export-hint" : undefined}
            title={hint || "Download failed and warning items as a Markdown file"}
            className={exportCls}
          >
            Export .md
          </button>
          <CopyButton
            getText={md}
            label="Copy as Markdown"
            disabled={!exportable}
            className="rounded-full px-4 py-2 text-sm"
          />
          <button
            type="button"
            onClick={onRunAgain}
            disabled={!canRun}
            className="rounded-full bg-pri px-5 py-2 font-semibold text-on-pri hover:brightness-110 focus:outline-none focus-visible:ring-2 focus-visible:ring-pri focus-visible:ring-offset-2 focus-visible:ring-offset-bg disabled:opacity-50"
          >
            Run again
          </button>
        </div>
        {hint && (
          <p id="export-hint" className="w-full text-right text-xs text-mut">
            {hint}
          </p>
        )}
      </header>

      <div aria-live="polite" className="space-y-2">
        {run.warning && <p className={`${notice} border-wa/50 bg-wa/10`}>Warning: {run.warning}</p>}
        {parsing && !timedOut && <Spinner text="Parsing manual…" />}
        {parsing && timedOut && (
          <p className={`${notice} border-wa/50 bg-wa/10`}>Parsing is taking too long. Stopped checking; reload to try again.</p>
        )}
        {status === "failed" && (
          <p role="alert" className={`${notice} border-fa/50 bg-fa/10 font-medium`}>
            {hasSweep ? "Run failed: " : "Failed: "}
            {run.error || "The run failed for an unknown reason."}
          </p>
        )}
        {running && !hasSweep && <Spinner text="Opening the site and discovering menus…" />}
        {status === "done" && sum && sum.total === 0 && <p className="text-mut">No menus were found on the site.</p>}
        {(status === "parsed" || status === "created") && !hasSweep && (
          <p className="text-mut">Ready. Press Run menu test on the left to start checking the site.</p>
        )}
      </div>
      {problem && (
        <p role="alert" className={`${notice} border-fa/50 bg-fa/10 text-fa`}>
          {problem}
        </p>
      )}
      {timedOut && running && (
        <p role="alert" className={`${notice} border-wa/50 bg-wa/10`}>
          Stopped checking after 20 minutes. Reload the page to see the latest state.
        </p>
      )}

      {hasSweep && sum && (
        <>
          <section aria-label="Score" className="rounded-xl border border-line bg-panel p-4">
            <div className="flex flex-wrap items-center gap-x-8 gap-y-4">
              <ScoreRing sum={sum} />
              <dl className="grid grid-cols-4 gap-x-6 gap-y-1 text-center sm:text-left">
                {(
                  [
                    ["Passed", sum.passed, "text-ok"],
                    ["Warning", sum.warning, "text-wa"],
                    ["Failed", sum.failed, "text-fa"],
                    ["Left", sum.pending, "text-ink"],
                  ] as const
                ).map(([l, n, c]) => (
                  <div key={l} className="flex flex-col-reverse">
                    <dt className="text-xs text-mut">{l}</dt>
                    <dd className={`font-display text-3xl font-bold ${c}`}>{n}</dd>
                  </div>
                ))}
              </dl>
            </div>
            <div className="mt-4">
              <p className="text-xs text-mut">
                {doneCount} of {sum.total} checks done (menus, forms and page actions){status === "done" && ", finished"}
              </p>
              <div
                role="progressbar"
                aria-label="Checks done"
                aria-valuemin={0}
                aria-valuemax={sum.total}
                aria-valuenow={doneCount}
                className="mt-1 flex h-2 overflow-hidden rounded-full bg-panel2"
              >
                <div className="bg-ok" style={{ width: pct(sum.passed) }} />
                <div className="bg-wa" style={{ width: pct(sum.warning) }} />
                <div className="bg-fa" style={{ width: pct(sum.failed) }} />
              </div>
            </div>
          </section>

          {data?.note && isTimeStop(data.note) && (
            <p role="status" className={`${notice} border-wa/60 bg-wa/15 font-medium`}>
              <span aria-hidden="true">⏱ </span>
              {data.note}
            </p>
          )}
          {data?.note && !isTimeStop(data.note) && <p className={`${notice} border-wa/50 bg-wa/10`}>{data.note}</p>}

          <IssuesSummary issues={issues} />

          <section aria-labelledby="results-h" className="space-y-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h3 id="results-h" className="font-display text-base font-semibold">
                Results
              </h3>
              <div role="group" aria-label="Filter results" className="flex gap-1 rounded-lg bg-panel2 p-1">
                {FILTERS.map((f) => (
                  <button
                    key={f.key}
                    type="button"
                    aria-pressed={filter === f.key}
                    onClick={() => setFilter(f.key)}
                    className={`rounded-md px-3 py-1 text-xs font-semibold focus:outline-none focus-visible:ring-2 focus-visible:ring-pri ${
                      filter === f.key ? "bg-pri text-on-pri" : "text-mut hover:text-ink"
                    }`}
                  >
                    {f.label} <span className="font-mono opacity-80">{counts[f.key]}</span>
                  </button>
                ))}
              </div>
            </div>
            {shown.length === 0 ? (
              <p className="rounded-xl border border-line bg-panel px-4 py-6 text-center text-mut">
                Nothing matches this filter.
              </p>
            ) : (
              <ol className="divide-y divide-line overflow-hidden rounded-xl border border-line bg-panel">
                {shown.map(({ menu, forms, actions }) => (
                  <li key={menu.id}>
                    <ResultRow st={menu} />
                    {forms.length > 0 && <FormList forms={forms} forceOpen={filter !== "all"} />}
                    {actions.length > 0 && <PageActions actions={actions} forceOpen={filter !== "all"} />}
                  </li>
                ))}
              </ol>
            )}
          </section>
        </>
      )}

      {data && !parsing && <ManualSteps data={data} manual={manual} />}
    </main>
  );
}
