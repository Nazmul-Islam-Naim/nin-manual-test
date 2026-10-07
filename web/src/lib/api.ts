// Single place for backend access (contract 001). Base URL from NEXT_PUBLIC_API_URL.
export const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/$/, "");

export type SourceType = "text" | "pdf" | "docx" | "md" | "txt";
export type ManualSummary = {
  id: string;
  source_type: SourceType;
  original_filename: string | null;
  char_count: number;
  created_at: string;
};
export type Manual = ManualSummary & { text: string };

export const ALLOWED_EXT = [".pdf", ".docx", ".md", ".txt"];
export const MAX_UPLOAD_BYTES = 10 * 1024 * 1024;

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
  ) {
    super(message);
  }
}

// Fallback messages when the server gives none; server `error.message` wins.
const FALLBACK: Record<string, string> = {
  file_too_large: "File is larger than 10 MB.",
  unsupported_file_type: "Unsupported file type. Use .pdf, .docx, .md or .txt.",
  empty_text: "The text is empty.",
  no_readable_text: "No readable text found in this file.",
  invalid_encoding: "The file is not valid UTF-8.",
  invalid_request: "Invalid request. Provide text or a readable file.",
  manual_not_found: "Manual not found.",
  test_run_not_found: "Test run not found.",
  invalid_url: "Enter a valid http(s) URL.",
  url_unreachable: "The site could not be reached.",
  private_url_blocked: "Private or local URLs are blocked.",
  run_busy: "This run is already busy. Wait for it to finish.",
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, init);
  } catch {
    throw new ApiError(0, "network_error", `Cannot reach the server at ${API_URL}. Is the backend running?`);
  }
  if (res.ok) return (await res.json()) as T;
  let code = "unknown_error";
  let message = `Request failed (${res.status}).`;
  try {
    const body = await res.json();
    if (body?.error?.code) {
      code = body.error.code;
      message = body.error.message || FALLBACK[code] || message;
    }
  } catch {
    // proxy-level errors may have no JSON body
    if (res.status === 413) {
      code = "file_too_large";
      message = FALLBACK[code];
    }
  }
  throw new ApiError(res.status, code, message);
}

export function createManual(input: { text: string } | { file: File }): Promise<ManualSummary> {
  if ("file" in input) {
    const fd = new FormData();
    fd.append("file", input.file);
    return request("/manuals", { method: "POST", body: fd });
  }
  return request("/manuals", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text: input.text }),
  });
}

export const getManual = (id: string) => request<Manual>(`/manuals/${encodeURIComponent(id)}`);

// Contract 002
export type TestRun = {
  id: string;
  manual_id: string;
  base_url: string;
  status: "created" | "parsing" | "parsed" | "running" | "done" | "failed";
  error?: string | null;
  created_at: string;
  warning?: string | null;
  // Contract 004 addendum e: optional, absent on old runs
  started_at?: string | null;
  finished_at?: string | null;
  max_minutes?: number | null;
};

export const createTestRun = (manual_id: string, url: string) =>
  request<TestRun>("/test-runs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ manual_id, url }),
  });

export const getTestRun = (id: string) => request<TestRun>(`/test-runs/${encodeURIComponent(id)}`);

// Contract 003
export type StepAction =
  | "open" | "click" | "type" | "select" | "check" | "assert_text" | "assert_visible" | "wait" | "visit_menu" | "submit_form" | "click_action"; // click_action: addendum d
// Contract 004 (+ addendum b: error details; all new fields optional, old data may lack them)
export type ErrorType =
  | "server_error" | "client_error" | "error_page" | "blank_page" | "timeout" | "navigation_failed"
  | "console_error" | "failed_request" | "validation_missing" | "no_reaction" | "form_error_banner"
  | "browser_validation_blocked" | "file_input_skipped" | "crash" | "interrupted"
  | "invalid_accepted" | "valid_rejected" | "xss_risk" | "sql_error" // addendum c
  | "action_no_effect" // addendum d
  | "submit_blocked" | "permission_denied" | "possible_duplicate"; // addendum f
export type ConsoleMessage = { type: "error" | "pageerror"; text: string; location: string | null };
export type FailedRequest = { method: string; url: string; status: number };
export type ResultDetails = {
  console_messages?: ConsoleMessage[];
  failed_requests?: FailedRequest[];
  excerpt?: string | null;
};
export type StepResult = {
  error_type?: ErrorType | null;
  page_url?: string | null;
  details?: ResultDetails | null;
  status: "running" | "passed" | "failed" | "warning";
  error: string | null;
  http_status: number | null;
  console_errors: number;
  failed_requests: number;
  duration_ms: number | null;
};
export type SweepSummary = { total: number; passed: number; failed: number; warning: number; pending: number };
// Contract 004 addendum c: validation-matrix case info (null/absent for menus and old data)
export type StepMeta = {
  kind: "valid" | "invalid" | "security" | "tolerant" | "action";
  category: string;
  field: string | null;
  form: string | null;
  source: "auto" | "manual";
};
// Contract 003 addendum: rules the manual states
export type FieldRule = { field: string; rule: string | null; valid: string[]; invalid: string[] };
export type ValidationDepth = "basic" | "standard" | "thorough";
export type Step = {
  meta?: StepMeta | null;
  result?: StepResult | null;
  id: string;
  order: number;
  action: StepAction;
  target: string;
  value: string | null;
  expected: string | null;
  unclear: boolean;
};
export type TestCase = { id: string; title: string; order: number; steps: Step[] };
export type RunSteps = {
  run_id: string;
  status: TestRun["status"];
  test_cases: TestCase[];
  summary?: SweepSummary;
  note?: string | null;
  field_rules?: FieldRule[];
  started_at?: string | null;
  finished_at?: string | null;
  max_minutes?: number | null;
};

export const getRunSteps = (id: string) => request<RunSteps>(`/test-runs/${encodeURIComponent(id)}/steps`);

export const executeRun = (id: string, credentials: { username: string; password: string } | null, submit_forms = true, validation_depth?: ValidationDepth, test_actions = true, max_minutes?: number, fast_mode = false) =>
  request<{ id: string; status: TestRun["status"] }>(`/test-runs/${encodeURIComponent(id)}/execute`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ credentials, submit_forms, test_actions, fast_mode, ...(max_minutes ? { max_minutes } : {}), ...(submit_forms && validation_depth ? { validation_depth } : {}) }),
  });
