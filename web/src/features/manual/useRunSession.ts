"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  ApiError,
  createManual,
  createTestRun,
  executeRun,
  getRunSteps,
  getTestRun,
  type ManualSummary,
  type RunSteps,
  type ValidationDepth,
  type TestRun,
} from "@/lib/api";

const POLL_MS = 2000;
const PARSE_GIVE_UP_MS = 5 * 60 * 1000;
const RUN_GIVE_UP_MS = 20 * 60 * 1000; // minimum; extended by the run time limit + 10 min

export const errMsg = (err: unknown) => (err instanceof ApiError ? err.message : "Something went wrong.");

export type ManualInput = { key: string; input: { text: string } | { file: File } };

// Owns the run: create manual + run, execute the sweep, and poll run + steps every 2 s while active.
export function useRunSession() {
  const [run, setRun] = useState<TestRun | null>(null);
  const [data, setData] = useState<RunSteps | null>(null);
  const [manual, setManual] = useState<{ key: string; summary: ManualSummary } | null>(null);
  const [startedAt, setStartedAt] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const [timedOut, setTimedOut] = useState(false);
  const [pollGen, setPollGen] = useState(0);
  const runId = run?.id;
  const limitMin = useRef(0);

  useEffect(() => {
    if (!runId) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;
    const started = Date.now();

    async function tick() {
      let keepGoing = true;
      let active = "running";
      try {
        const [r, s] = await Promise.all([getTestRun(runId!), getRunSteps(runId!)]);
        if (cancelled) return;
        setRun(r);
        setData(s);
        setProblem(null);
        active = r.status;
        limitMin.current = r.max_minutes ?? s.max_minutes ?? 0;
        keepGoing = r.status === "running" || r.status === "parsing" || r.status === "created";
      } catch (err) {
        if (cancelled) return;
        setProblem(errMsg(err)); // transient network errors keep polling; 404 stops
        if (err instanceof ApiError && err.status === 404) keepGoing = false;
      }
      if (!keepGoing) return;
      if (Date.now() - started > (active === "running" ? Math.max(RUN_GIVE_UP_MS, (limitMin.current + 10) * 60 * 1000) : PARSE_GIVE_UP_MS)) {
        return setTimedOut(true);
      }
      timer = setTimeout(tick, POLL_MS);
    }

    tick();
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [runId, pollGen]);

  // Throws ApiError; the caller maps it to field errors.
  const start = useCallback(
    async (m: ManualInput, url: string) => {
      setStarting(true);
      try {
        let summary = manual?.key === m.key ? manual.summary : null; // reuse the manual id when input is unchanged
        if (!summary) {
          summary = await createManual(m.input);
          setManual({ key: m.key, summary });
        }
        try {
          const r = await createTestRun(summary.id, url);
          setData(null);
          setProblem(null);
          setTimedOut(false);
          setRun(r);
          setStartedAt(r.created_at);
          setPollGen((g) => g + 1);
        } catch (err) {
          if (err instanceof ApiError && err.code === "manual_not_found") setManual(null);
          throw err;
        }
      } finally {
        setStarting(false);
      }
    },
    [manual],
  );

  const execute = useCallback(
    async (credentials: { username: string; password: string } | null, submitForms: boolean, depth?: ValidationDepth, testActions = true, maxMinutes?: number, fastMode = false) => {
      if (!runId) return;
      setProblem(null);
      setTimedOut(false);
      setStarting(true);
      try {
        await executeRun(runId, credentials, submitForms, depth, testActions, maxMinutes, fastMode);
        setRun((r) => (r ? { ...r, status: "running", error: null } : r));
        // drop the previous sweep, keep the manual test cases
        setData((d) => (d ? { ...d, test_cases: d.test_cases.filter((tc) => tc.title !== "Menu sweep"), summary: undefined, note: null } : d));
        setPollGen((g) => g + 1);
      } catch (err) {
        setProblem(errMsg(err));
        if (err instanceof ApiError && err.code === "run_busy") {
          setRun((r) => (r ? { ...r, status: "running" } : r)); // 409 means it is really running
          setPollGen((g) => g + 1);
        }
      } finally {
        setStarting(false);
      }
    },
    [runId],
  );

  return { run, data, manual: manual?.summary ?? null, startedAt, starting, problem, timedOut, start, execute };
}
