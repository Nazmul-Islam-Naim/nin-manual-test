import type { Issue } from "./model";

export default function IssuesSummary({ issues }: { issues: Issue[] }) {
  if (issues.length === 0) return null;
  return (
    <section aria-labelledby="issues-h" className="rounded-xl border border-line bg-panel p-4">
      <h3 id="issues-h" className="font-display text-base font-semibold">
        Issues to fix
      </h3>
      <ul className="mt-2 grid gap-2 sm:grid-cols-2">
        {issues.map((i) => (
          <li key={i.key} className="flex items-center gap-2 rounded-lg border border-line bg-panel2 px-3 py-2">
            <span
              aria-hidden="true"
              className={`grid size-5 shrink-0 place-items-center rounded-full text-xs font-bold ${
                i.status === "failed" ? "bg-fa/15 text-fa" : "bg-wa/15 text-wa"
              }`}
            >
              {i.status === "failed" ? "✕" : "!"}
            </span>
            <span className="min-w-0 flex-1 wrap-break-word">
              {i.title} <span className="sr-only">({i.status})</span>
            </span>
            <span className="font-mono text-sm font-semibold">{i.count}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}
