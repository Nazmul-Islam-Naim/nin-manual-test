"use client";

import { useState } from "react";
import type { Step } from "@/lib/api";
import StatusChip from "@/components/ui/StatusChip";
import ErrorDetail from "./ErrorDetail";
import { statusOf } from "./model";

const plural = (n: number, w: string) => `${n} ${w}${n === 1 ? "" : "s"}`;

const CAT: Record<string, string> = { valid_sample: "valid", manual_valid: "valid", manual_invalid: "invalid", xss: "XSS", sqli: "SQL" };

// Page-action icon + spoken name per meta.category (addendum d); unknown categories fall back to a button.
const ACTION_ICON: Record<string, [string, string]> = {
  action_link: ["↗", "Link"],
  action_button: ["◉", "Button"],
  action_tab: ["▭", "Tab"],
  action_row: ["☰", "Row action"],
  action_pagination: ["⇄", "Pagination"],
};

export default function ResultRow({ st, form, kase, action }: { st: Step; form?: boolean; kase?: boolean; action?: boolean }) {
  const [open, setOpen] = useState(false);
  const k = statusOf(st);
  const r = st.result;
  const expandable = k === "failed" || k === "warning";
  const meta = r
    ? [
        r.http_status ? `HTTP ${r.http_status}` : null,
        r.console_errors > 0 ? plural(r.console_errors, "console error") : null,
        r.failed_requests > 0 ? plural(r.failed_requests, "failed request") : null,
        r.duration_ms != null ? `${(r.duration_ms / 1000).toFixed(1)} s` : null,
      ].filter(Boolean)
    : [];
  const detailId = `detail-${st.id}`;
  const [icon, iconName] = ACTION_ICON[st.meta?.category ?? ""] ?? ACTION_ICON.action_button;
  const actionLabel = st.target.includes(" > ") ? st.target.split(" > ").slice(1).join(" > ") : st.target;

  const body = (
    <>
      <StatusChip k={k} />
      <span className="w-full min-w-0 sm:w-auto sm:flex-1">
        <span className="block wrap-break-word font-medium">
          {kase && st.meta ? (
            <>
              <span className="mr-2 rounded border border-line bg-panel2 px-1.5 py-0.5 text-[11px] font-semibold uppercase tracking-wide text-mut">
                {CAT[st.meta.category] ?? st.meta.category}
              </span>
              <span
                className={`mr-2 rounded border px-1.5 py-0.5 text-[11px] font-semibold ${
                  st.meta.source === "manual" ? "border-pri/50 bg-pri/10 text-pri" : "border-line text-mut"
                }`}
              >
                {st.meta.source === "manual" ? "manual" : "auto"}
              </span>
              <span className="font-mono text-[13px] font-normal">{st.value ?? "(no data)"}</span>
            </>
          ) : action ? (
            <>
              <span
                title={iconName}
                className="mr-2 inline-grid size-5 place-items-center rounded border border-line bg-panel2 align-middle text-[11px] text-mut"
              >
                <span aria-hidden="true">{icon}</span>
                <span className="sr-only">{iconName}: </span>
              </span>
              {actionLabel}
            </>
          ) : (
            <>
              {form && (
                <span aria-hidden="true" className="mr-1.5 text-mut">
                  ▤
                </span>
              )}
              {st.target}
            </>
          )}
        </span>
        <span className="block break-all font-mono text-xs text-mut">
          {kase
            ? `Expected: ${st.expected ?? "-"}`
            : form
              ? st.value === "empty"
                ? "form · empty submit"
                : "form · sample data"
              : st.value}
        </span>
        {r?.error && k !== "passed" && <span className="mt-0.5 block wrap-break-word text-xs">{r.error}</span>}
      </span>
      {meta.length > 0 && <span className="shrink-0 font-mono text-xs text-mut sm:text-right">{meta.join(" · ")}</span>}
      {expandable && (
        <span aria-hidden="true" className="shrink-0 text-mut">
          {open ? "▾" : "▸"}
        </span>
      )}
    </>
  );
  const cls = "flex w-full flex-col items-start gap-1 px-4 py-3 text-left sm:flex-row sm:items-center sm:gap-3";

  return (
    <div>
      {expandable ? (
        <button
          type="button"
          aria-expanded={open}
          aria-controls={detailId}
          onClick={() => setOpen((v) => !v)}
          className={`${cls} hover:bg-panel2 focus:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-pri`}
        >
          {body}
        </button>
      ) : (
        <div className={cls}>{body}</div>
      )}
      {expandable && open && <ErrorDetail st={st} id={detailId} />}
    </div>
  );
}
