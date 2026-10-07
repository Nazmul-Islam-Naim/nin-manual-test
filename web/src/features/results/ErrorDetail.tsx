import type { Step } from "@/lib/api";
import CopyButton from "@/components/ui/CopyButton";
import { infoFor } from "./errorInfo";
import { detailText } from "./model";

const mono = "break-all font-mono text-xs";

function Item({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid gap-1 sm:grid-cols-[8rem_1fr] sm:gap-3">
      <dt className="text-xs font-medium uppercase tracking-wide text-mut">{label}</dt>
      <dd className="min-w-0">{children}</dd>
    </div>
  );
}

export default function ErrorDetail({ st, id }: { st: Step; id: string }) {
  const r = st.result;
  if (!r || (r.status !== "failed" && r.status !== "warning")) return null;
  const info = infoFor(r.error_type, r.status);
  const d = r.details;
  const cm = d?.console_messages ?? [];
  const fr = d?.failed_requests ?? [];
  const hasEvidence =
    r.page_url || r.http_status || r.error || d?.excerpt || cm.length || fr.length || r.duration_ms != null ||
    r.console_errors > 0 || r.failed_requests > 0;

  return (
    <div id={id} className="space-y-4 border-t border-line bg-bg/50 px-4 py-4">
      <div>
        <h4 className="font-display text-base font-semibold">{info.title}</h4>
        <p className="mt-1 max-w-prose text-mut">{info.explain}</p>
      </div>

      <div>
        <h5 className="text-xs font-semibold uppercase tracking-wide text-mut">What to check</h5>
        <ul className="mt-1 list-disc space-y-0.5 pl-5">
          {info.check.map((c) => (
            <li key={c}>{c}</li>
          ))}
        </ul>
      </div>

      <div>
        <h5 className="text-xs font-semibold uppercase tracking-wide text-mut">Evidence</h5>
        {hasEvidence ? (
          <dl className="mt-2 space-y-2 rounded-lg border border-line bg-panel p-3">
            {r.error && (
              <Item label="Message">
                <span className="wrap-break-word">{r.error}</span>
              </Item>
            )}
            {r.page_url && (
              <Item label="Page URL">
                <span className={mono}>{r.page_url}</span>
              </Item>
            )}
            {r.http_status ? (
              <Item label="HTTP status">
                <span className={mono}>{r.http_status}</span>
              </Item>
            ) : null}
            {r.duration_ms != null && (
              <Item label="Duration">
                <span className={mono}>{(r.duration_ms / 1000).toFixed(1)} s</span>
              </Item>
            )}
            {d?.excerpt && (
              <Item label="Excerpt">
                <q className="wrap-break-word italic">{d.excerpt}</q>
              </Item>
            )}
            {cm.length > 0 && (
              <Item label={`Console (${Math.max(r.console_errors, cm.length)})`}>
                <ul className="space-y-1">
                  {cm.map((m, i) => (
                    <li key={i} className={`${mono} rounded bg-panel2 px-2 py-1`}>
                      <span className="font-semibold text-fa">[{m.type}]</span> {m.text}
                      {m.location && <span className="block text-mut">{m.location}</span>}
                    </li>
                  ))}
                </ul>
              </Item>
            )}
            {fr.length > 0 && (
              <Item label={`Failed requests (${Math.max(r.failed_requests, fr.length)})`}>
                <ul className="space-y-1">
                  {fr.map((q, i) => (
                    <li key={i} className={`${mono} rounded bg-panel2 px-2 py-1`}>
                      <span className="font-semibold">{q.method}</span> {q.url}{" "}
                      <span className="font-semibold text-fa">{q.status || "network failure"}</span>
                    </li>
                  ))}
                </ul>
              </Item>
            )}
            {cm.length === 0 && r.console_errors > 0 && (
              <Item label="Console errors">
                <span className={mono}>{r.console_errors}</span>
              </Item>
            )}
            {fr.length === 0 && r.failed_requests > 0 && (
              <Item label="Failed requests">
                <span className={mono}>{r.failed_requests}</span>
              </Item>
            )}
          </dl>
        ) : (
          <p className="mt-1 text-mut">No further evidence was recorded.</p>
        )}
      </div>

      <CopyButton getText={() => detailText(st)} />
    </div>
  );
}
