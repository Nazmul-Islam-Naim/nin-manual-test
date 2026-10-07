"use client";

import { useState } from "react";
import ResultsPanel from "@/features/results/ResultsPanel";
import SetupPanel, { type RunOptions } from "./SetupPanel";
import { useRunSession } from "./useRunSession";

export default function TestRunner() {
  const s = useRunSession();
  const [opts, setOpts] = useState<RunOptions>({ username: "", password: "", submitForms: true, depth: "thorough", testActions: true, maxMinutes: 60, fastMode: false });
  const sweeping = s.run?.status === "running";

  const execute = () => {
    const creds = opts.username.trim() || opts.password ? { username: opts.username, password: opts.password } : null;
    return s.execute(creds, opts.submitForms, opts.depth, opts.testActions, opts.maxMinutes, opts.fastMode);
  };

  return (
    <div className="min-h-screen lg:grid lg:grid-cols-[340px_1fr]">
      <SetupPanel
        opts={opts}
        setOpts={setOpts}
        hasRun={!!s.run}
        starting={s.starting}
        sweeping={sweeping}
        onStart={s.start}
        onExecute={execute}
      />
      <ResultsPanel
        key={s.run?.id ?? "none"}
        run={s.run}
        data={s.data}
        manual={s.manual}
        startedAt={s.startedAt}
        problem={s.problem}
        timedOut={s.timedOut}
        canRun={!!s.run && !sweeping && !s.starting}
        onRunAgain={execute}
      />
    </div>
  );
}
