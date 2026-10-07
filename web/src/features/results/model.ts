import type { RunSteps, Step, SweepSummary, TestRun } from "@/lib/api";
import type { ChipKey } from "@/components/ui/StatusChip";
import { infoFor } from "./errorInfo";

// A page action (click_action) with the forms it opened (modal/drawer/new page).
export type ActionGroup = { action: Step; forms: Step[] };
export type Group = { menu: Step; forms: Step[]; actions: ActionGroup[] };
export type Filter = "all" | "failed" | "warning" | "passed";

export const statusOf = (st: Step): ChipKey => st.result?.status ?? "pending";

// Menu steps, each followed by its own forms, then its page actions (each with the forms it opened). Backend order.
export function sweepGroups(data: RunSteps | null): Group[] {
  const sweep = data?.test_cases.find((tc) => tc.title === "Menu sweep");
  const groups: Group[] = [];
  for (const st of sweep?.steps ?? []) {
    if (st.action === "visit_menu") groups.push({ menu: st, forms: [], actions: [] });
    else if (st.action === "click_action") groups.at(-1)?.actions.push({ action: st, forms: [] });
    else if (st.action === "submit_form") {
      const g = groups.at(-1);
      (g?.actions.at(-1)?.forms ?? g?.forms)?.push(st);
    }
  }
  return groups;
}

const matches = (st: Step, f: Filter) => f === "all" || statusOf(st) === f;

// A menu (or action) stays visible as context when something under it matches.
export function visibleGroups(groups: Group[], f: Filter): Group[] {
  if (f === "all") return groups;
  return groups
    .map((g) => ({
      menu: g.menu,
      forms: g.forms.filter((s) => matches(s, f)),
      actions: g.actions
        .map((a) => ({ action: a.action, forms: a.forms.filter((s) => matches(s, f)) }))
        .filter((a) => matches(a.action, f) || a.forms.length > 0),
    }))
    .filter((g) => matches(g.menu, f) || g.forms.length > 0 || g.actions.length > 0);
}

// Every step of a group in report order.
export const stepsOf = (g: Group): Step[] => [g.menu, ...g.forms, ...g.actions.flatMap((a) => [a.action, ...a.forms])];

// Validation-matrix cases (addendum c) carry meta.field; empty/sample steps and legacy steps stay plain rows.
export type FieldGroup = { field: string; cases: Step[] };
export type FormGroup = { form: string; fields: FieldGroup[]; steps: Step[] };

export function splitForms(forms: Step[]): { plain: Step[]; byForm: FormGroup[] } {
  const plain: Step[] = [];
  const byForm: FormGroup[] = [];
  for (const st of forms) {
    const field = st.meta?.field;
    if (!field) {
      plain.push(st);
      continue;
    }
    const name = st.meta?.form || st.target.split(" > ").at(-2) || "Form";
    let fg = byForm.find((g) => g.form === name);
    if (!fg) byForm.push((fg = { form: name, fields: [], steps: [] }));
    fg.steps.push(st);
    let fd = fg.fields.find((f) => f.field === field);
    if (!fd) fg.fields.push((fd = { field, cases: [] }));
    fd.cases.push(st);
  }
  return { plain, byForm };
}

export function countOf(steps: Step[]) {
  const c = { passed: 0, warning: 0, failed: 0, other: 0 };
  for (const st of steps) {
    const k = statusOf(st);
    if (k === "passed" || k === "warning" || k === "failed") c[k]++;
    else c.other++;
  }
  return c;
}

export type Issue = { key: string; title: string; status: "failed" | "warning"; count: number };

// Failed/warning rows grouped by error_type (rows without one fall into a fallback group).
export function issuesOf(groups: Group[]): Issue[] {
  const map = new Map<string, Issue>();
  for (const st of groups.flatMap(stepsOf)) {
    const r = st.result;
    if (!r || (r.status !== "failed" && r.status !== "warning")) continue;
    const key = `${r.status}:${r.error_type ?? "other"}`;
    const hit = map.get(key);
    if (hit) hit.count++;
    else map.set(key, { key, title: infoFor(r.error_type, r.status).title, status: r.status, count: 1 });
  }
  return [...map.values()].sort((a, b) => (a.status === b.status ? b.count - a.count : a.status === "failed" ? -1 : 1));
}

// Evidence lines shared by "Copy details" and the Markdown export.
type Evidence = { label: string; value?: string; list?: string[] };

function evidenceOf(st: Step): Evidence[] {
  const r = st.result;
  if (!r) return [];
  const d = r.details;
  const kase = !!st.meta?.field;
  const ev: Evidence[] = [];
  if (kase) ev.push({ label: "Data used", value: st.value ?? "" });
  if (kase && st.expected) ev.push({ label: "Expected", value: st.expected });
  if (kase && st.meta) ev.push({ label: "Source", value: st.meta.source });
  if (r.error) ev.push({ label: "Message", value: r.error });
  if (r.page_url) ev.push({ label: "Page", value: r.page_url });
  if (r.http_status) ev.push({ label: "HTTP status", value: String(r.http_status) });
  if (r.duration_ms != null) ev.push({ label: "Duration", value: `${r.duration_ms} ms` });
  if (d?.excerpt) ev.push({ label: "Excerpt", value: d.excerpt });
  if (d?.console_messages?.length) {
    ev.push({
      label: "Console messages",
      list: d.console_messages.map((m) => `[${m.type}] ${m.text}${m.location ? ` (${m.location})` : ""}`),
    });
  }
  if (d?.failed_requests?.length) {
    ev.push({
      label: "Failed requests",
      list: d.failed_requests.map((q) => `${q.method} ${q.url} -> ${q.status || "network failure"}`),
    });
  }
  return ev;
}

export function detailText(st: Step): string {
  const r = st.result;
  if (!r) return "";
  const info = infoFor(r.error_type, r.status === "warning" ? "warning" : "failed");
  return [
    `${r.status.toUpperCase()}: ${st.target}`,
    `Type: ${info.title}${r.error_type ? ` (${r.error_type})` : ""}`,
    ...evidenceOf(st).map((e) =>
      e.list ? `${e.label}:\n${e.list.map((l) => `  ${l}`).join("\n")}` : `${e.label}: ${e.value}`,
    ),
  ].join("\n");
}

// mm:ss (minutes may exceed 59)
export function fmtClock(ms: number): string {
  const s = Math.max(0, Math.floor(ms / 1000));
  return `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
}
export const isTimeStop = (note?: string | null) => !!note && note.includes("Stopped at the time limit");

// ---- Markdown export (instruction 014) ----
const MD_MAX = 500;
const flat = (s: string) => s.replace(/\s+/g, " ").trim();
const cut = (s: string) => (s.length > MD_MAX ? `${s.slice(0, MD_MAX)}…` : s);
// Plain text: escape markdown and table syntax, collapse whitespace, truncate.
const esc = (s: string) => cut(flat(s)).replace(/([\\`*_[\]<>|#])/g, "\\$1");
// Code span: backticks cannot be escaped inside one, so swap them for a look-alike.
const code = (s: string) => `\`${cut(flat(s)).replace(/`/g, "ˋ")}\``;

export function buildMarkdown(run: TestRun, steps: RunSteps | null, summary: SweepSummary, note?: string | null): string {
  const groups = sweepGroups(steps);
  const started = run.started_at ?? steps?.started_at;
  const finished = run.finished_at ?? steps?.finished_at;
  const ms = started && finished ? Date.parse(finished) - Date.parse(started) : NaN;
  const duration = ms >= 0 ? fmtClock(ms) : null;
  const out: string[] = [
    "# Test report",
    "",
    `- URL: ${code(run.base_url)}`,
    `- Run ID: ${code(run.id)}`,
    `- Started: ${code(started ?? run.created_at)}`,
    ...(finished ? [`- Finished: ${code(finished)}`] : []),
    ...(duration ? [`- Duration: ${code(duration)}`] : []),
    `- Status: ${esc(run.status)}`,
    "",
    "## Summary",
    "",
    "| Total | Passed | Warning | Failed | Left |",
    "| ---: | ---: | ---: | ---: | ---: |",
    `| ${summary.total} | ${summary.passed} | ${summary.warning} | ${summary.failed} | ${summary.pending} |`,
    "",
    "## Note and limits",
    "",
  ];
  if (note) out.push(`- ${esc(note)}`);
  out.push(
    "- Only failed and warning items are listed below. Passed items are counted only.",
    `- Long text is cut to ${MD_MAX} characters.`,
    "",
  );

  const issues = issuesOf(groups);
  if (issues.length) {
    out.push("## Issues to fix", "", "| Type | Status | Count |", "| --- | --- | ---: |");
    for (const i of issues) out.push(`| ${esc(i.title)} | ${i.status} | ${i.count} |`);
    out.push("");
  }

  for (const status of ["failed", "warning"] as const) {
    out.push(`## ${status === "failed" ? "Failed" : "Warning"}`, "");
    let any = false;
    for (const g of groups) {
      const items = stepsOf(g).filter((s) => s.result?.status === status);
      if (!items.length) continue;
      any = true;
      out.push(`### ${esc(g.menu.target)}`, "");
      for (const st of items) {
        const r = st.result!;
        const info = infoFor(r.error_type, status);
        out.push(
          `#### ${esc(st.target)}`,
          "",
          `- Status: ${status}`,
          `- Error type: ${r.error_type ? `${code(r.error_type)} - ` : ""}${esc(info.title)}`,
          `- What happened: ${esc(info.explain)}`,
          "- What to check:",
          ...info.check.map((c) => `  - ${esc(c)}`),
        );
        const ev = evidenceOf(st);
        if (ev.length) {
          out.push("- Evidence:");
          for (const e of ev) {
            if (e.list) out.push(`  - ${e.label}:`, ...e.list.map((l) => `    - ${code(l)}`));
            else out.push(`  - ${e.label}: ${code(e.value ?? "")}`);
          }
        }
        out.push("");
      }
    }
    if (!any) out.push("None.", "");
  }
  return out.join("\n");
}
