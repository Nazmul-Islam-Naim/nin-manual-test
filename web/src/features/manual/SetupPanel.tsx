"use client";

import { useState } from "react";
import { ALLOWED_EXT, ApiError, MAX_UPLOAD_BYTES, type ValidationDepth } from "@/lib/api";
import ThemeToggle from "@/components/ui/ThemeToggle";
import type { ManualInput } from "./useRunSession";

export type RunOptions = { username: string; password: string; submitForms: boolean; depth: ValidationDepth; testActions: boolean; maxMinutes: number; fastMode: boolean };

const DURATIONS = [15, 30, 60, 120];

const DEPTH_HINT: Record<ValidationDepth, string> = {
  basic: "Empty and sample submit only. Fastest, least test data.",
  standard: "Adds format, boundary and blank checks. Takes longer and sends more invalid sample data.",
  thorough: "Adds special, long, XSS and SQL checks. Slowest, sends the most sample data; nothing destructive.",
};

type Mode = "text" | "file";
const URL_ERRORS = ["invalid_url", "url_unreachable", "private_url_blocked"];

const field =
  "w-full rounded-lg border border-line bg-panel2 px-3 py-2 font-mono text-[13px] text-ink placeholder:text-mut/70 focus:outline-none focus-visible:ring-2 focus-visible:ring-pri disabled:opacity-60";
const label = "mb-1 block text-xs font-medium uppercase tracking-wider text-mut";

function precheck(file: File): string | null {
  const ext = file.name.slice(file.name.lastIndexOf(".")).toLowerCase();
  if (!ALLOWED_EXT.includes(ext)) return "Unsupported file type. Use .pdf, .docx, .md or .txt.";
  if (file.size > MAX_UPLOAD_BYTES) return "File is larger than 10 MB.";
  return null;
}

type Props = {
  opts: RunOptions;
  setOpts: (o: RunOptions) => void;
  hasRun: boolean;
  starting: boolean;
  sweeping: boolean;
  onStart: (m: ManualInput, url: string) => Promise<void>;
  onExecute: () => void;
};

export default function SetupPanel({ opts, setOpts, hasRun, starting, sweeping, onStart, onExecute }: Props) {
  const [mode, setMode] = useState<Mode>("text");
  const [text, setText] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [url, setUrl] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [urlError, setUrlError] = useState<string | null>(null);
  const [showLogin, setShowLogin] = useState(false);
  const busy = starting || sweeping;

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setUrlError(null);
    let m: ManualInput;
    if (mode === "text") {
      if (!text.trim()) return setError("Enter some text first.");
      m = { key: `t:${text}`, input: { text } };
    } else {
      if (!file) return setError("Choose a file first.");
      const bad = precheck(file);
      if (bad) return setError(bad);
      m = { key: `f:${file.name}:${file.size}:${file.lastModified}`, input: { file } };
    }
    if (!url.trim()) return setUrlError("Enter the website URL.");
    try {
      await onStart(m, url);
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : "Something went wrong.";
      if (err instanceof ApiError && URL_ERRORS.includes(err.code)) setUrlError(msg);
      else setError(msg);
    }
  }

  const tab = (m: Mode, text: string) => (
    <button
      type="button"
      role="tab"
      id={`tab-${m}`}
      aria-selected={mode === m}
      aria-controls="manual-panel"
      onClick={() => {
        setMode(m);
        setError(null);
      }}
      className={`flex-1 rounded-md px-3 py-1.5 text-xs font-semibold focus:outline-none focus-visible:ring-2 focus-visible:ring-pri ${
        mode === m ? "bg-pri text-on-pri" : "text-mut hover:text-ink"
      }`}
    >
      {text}
    </button>
  );

  return (
    <aside className="flex flex-col gap-5 border-b border-line bg-panel p-5 lg:sticky lg:top-0 lg:h-screen lg:overflow-y-auto lg:border-r lg:border-b-0">
      <div className="flex items-center justify-between">
        <h1 className="font-mono text-[15px] font-semibold text-pri">
          &gt; test<span className="text-mut">_runner</span>
        </h1>
        <ThemeToggle />
      </div>

      <form onSubmit={submit} noValidate className="flex flex-col gap-5">
        <div>
          <span className={label} id="manual-h">
            Manual
          </span>
          <div role="tablist" aria-labelledby="manual-h" className="mb-2 flex gap-1 rounded-lg bg-panel2 p-1">
            {tab("text", "Paste text")}
            {tab("file", "Upload file")}
          </div>
          <div id="manual-panel" role="tabpanel" aria-labelledby={`tab-${mode}`}>
            {mode === "text" ? (
              <>
                <label htmlFor="manual-text" className="sr-only">
                  Manual text
                </label>
                <textarea
                  id="manual-text"
                  rows={7}
                  value={text}
                  placeholder="Paste the manual text here"
                  onChange={(e) => setText(e.target.value)}
                  aria-invalid={!!error}
                  aria-describedby={error ? "form-error" : undefined}
                  className={field}
                />
              </>
            ) : (
              <>
                <label htmlFor="manual-file" className="sr-only">
                  File (.pdf, .docx, .md, .txt, max 10 MB)
                </label>
                <input
                  id="manual-file"
                  type="file"
                  accept={ALLOWED_EXT.join(",")}
                  onChange={(e) => setFile(e.target.files?.[0] ?? null)}
                  aria-invalid={!!error}
                  aria-describedby={error ? "form-error" : "file-hint"}
                  className={`${field} file:mr-3 file:rounded file:border-0 file:bg-pri file:px-2.5 file:py-1 file:text-xs file:font-semibold file:text-on-pri`}
                />
                <p id="file-hint" className="mt-1 text-xs text-mut">
                  .pdf, .docx, .md, .txt, max 10 MB
                </p>
              </>
            )}
          </div>
        </div>

        <div>
          <label htmlFor="site-url" className={label}>
            Website
          </label>
          <input
            id="site-url"
            type="text"
            inputMode="url"
            autoComplete="url"
            placeholder="https://example.com"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            aria-invalid={!!urlError}
            aria-describedby={urlError ? "url-error" : undefined}
            className={field}
          />
          {urlError && (
            <p id="url-error" role="alert" className="mt-1 text-xs text-fa">
              {urlError}
            </p>
          )}
        </div>

        {error && (
          <p id="form-error" role="alert" className="rounded-lg border border-fa/40 bg-fa/10 px-3 py-2 text-fa">
            {error}
          </p>
        )}

        <button
          type="submit"
          disabled={busy}
          className={`rounded-lg px-4 py-2.5 text-sm font-bold focus:outline-none focus-visible:ring-2 focus-visible:ring-pri focus-visible:ring-offset-2 focus-visible:ring-offset-panel disabled:opacity-60 ${
            hasRun ? "border border-line text-ink hover:bg-panel2" : "bg-pri text-on-pri hover:brightness-110"
          }`}
        >
          {starting ? "Starting…" : hasRun ? "Start again with new input" : "Start"}
        </button>
      </form>

      {/* outside the form so Enter in the login inputs cannot submit it */}
      <div className="flex flex-col gap-4 border-t border-line pt-5">
        <div>
          <button
            type="button"
            aria-expanded={showLogin}
            aria-controls="sweep-login"
            onClick={() => setShowLogin((v) => !v)}
            className="rounded text-xs font-medium uppercase tracking-wider text-mut hover:text-ink focus:outline-none focus-visible:ring-2 focus-visible:ring-pri"
          >
            <span aria-hidden="true">{showLogin ? "▾ " : "▸ "}</span>Login (optional)
          </button>
          {/* hidden (not unmounted) so typed values survive collapsing */}
          <div id="sweep-login" hidden={!showLogin} className="mt-2 space-y-2">
            <label htmlFor="sweep-user" className="sr-only">
              Username
            </label>
            <input
              id="sweep-user"
              type="text"
              placeholder="username"
              autoComplete="off"
              value={opts.username}
              onChange={(e) => setOpts({ ...opts, username: e.target.value })}
              disabled={busy}
              className={field}
            />
            <label htmlFor="sweep-pass" className="sr-only">
              Password
            </label>
            <input
              id="sweep-pass"
              type="password"
              placeholder="password"
              autoComplete="new-password"
              value={opts.password}
              onChange={(e) => setOpts({ ...opts, password: e.target.value })}
              disabled={busy}
              className={field}
            />
            <p className="text-xs text-mut">Used only for this run. It is not saved.</p>
          </div>
        </div>

        <label className="flex items-start gap-2">
          <input
            type="checkbox"
            checked={opts.submitForms}
            onChange={(e) => setOpts({ ...opts, submitForms: e.target.checked })}
            disabled={busy}
            className="mt-0.5 size-4 accent-(--pri) focus-visible:ring-2 focus-visible:ring-pri"
          />
          <span>Also test forms (fills sample data and submits)</span>
        </label>

        <label className="flex items-start gap-2">
          <input
            type="checkbox"
            checked={opts.testActions}
            onChange={(e) => setOpts({ ...opts, testActions: e.target.checked })}
            disabled={busy}
            className="mt-0.5 size-4 accent-(--pri) focus-visible:ring-2 focus-visible:ring-pri"
          />
          <span>Also test buttons, tabs and links inside pages</span>
        </label>

        <div>
          <label htmlFor="sweep-depth" className={label}>
            Validation depth
          </label>
          <select
            id="sweep-depth"
            value={opts.depth}
            onChange={(e) => setOpts({ ...opts, depth: e.target.value as ValidationDepth })}
            disabled={busy || !opts.submitForms}
            aria-describedby="depth-hint"
            className={field}
          >
            <option value="basic">Basic</option>
            <option value="standard">Standard</option>
            <option value="thorough">Thorough</option>
          </select>
          <p id="depth-hint" className="mt-1 text-xs text-mut">
            {opts.submitForms
              ? DEPTH_HINT[opts.depth]
              : "Turn on “Also test forms” to use this."}
          </p>
        </div>

        <div>
          <label htmlFor="sweep-max" className={label}>
            Max duration
          </label>
          <select
            id="sweep-max"
            value={opts.maxMinutes}
            onChange={(e) => setOpts({ ...opts, maxMinutes: Number(e.target.value) })}
            disabled={busy}
            aria-describedby="max-hint"
            className={field}
          >
            {DURATIONS.map((m) => (
              <option key={m} value={m}>
                {m} minutes
              </option>
            ))}
          </select>
          <p id="max-hint" className="mt-1 text-xs text-mut">
            The run stops at this limit and stays “done”; checks not reached are left pending.
          </p>
        </div>

        <label className="flex items-start gap-2">
          <input
            type="checkbox"
            checked={opts.fastMode}
            onChange={(e) => setOpts({ ...opts, fastMode: e.target.checked })}
            disabled={busy}
            aria-describedby="fast-hint"
            className="mt-0.5 size-4 accent-(--pri) focus-visible:ring-2 focus-visible:ring-pri"
          />
          <span>
            Fast mode
            <span id="fast-hint" className="block text-xs text-mut">
              No pauses between actions. Quicker, but harder to watch in the browser window.
            </span>
          </span>
        </label>

        <p className="text-xs text-mut">A Chromium window opens on this computer. Please do not close it.</p>

        <button
          type="button"
          onClick={onExecute}
          disabled={!hasRun || busy}
          className="rounded-lg bg-pri px-4 py-2.5 text-sm font-bold text-on-pri hover:brightness-110 focus:outline-none focus-visible:ring-2 focus-visible:ring-pri focus-visible:ring-offset-2 focus-visible:ring-offset-panel disabled:opacity-50"
        >
          {starting ? "Starting…" : sweeping ? "Running…" : "Run menu test"}
        </button>
        {!hasRun && <p className="-mt-2 text-xs text-mut">Press Start first to create a run.</p>}
      </div>
    </aside>
  );
}
