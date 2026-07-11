/** Mirrors FastAPI Pydantic models — single contract with backend. */

export type IngestStatus = "ready" | "processing" | "failed";

export type IngestStatusResponse = {
  job_id: string;
  repo_id: string;
  ref: string;
  commit_hash: string | null;
  sync_status: string;
  ready: boolean;
  error: string | null;
  error_reason?: string;
  files_parsed: number;
  chunks_created: number;
  asset_repo_id: string;
  graph_truncated: boolean;
  has_circular_dependencies: boolean;
  status: IngestStatus;
};

export type IngestResponse = {
  job_id: string;
  status: "processing" | "already_running";
};

export type ChatSource = {
  file_path: string;
  function_name: string;
  start_line: number;
  end_line: number;
  lines?: number;
};

export type AgentTraceStep = {
  state: string;
};

export type ChatResponse = {
  answer: string;
  sources: ChatSource[];
  confidence_score: number;
  gated: boolean;
  cache_hit?: boolean;
  rate_limited?: boolean;
  retry_after_s?: number;
  timed_out?: boolean;
  groq_calls?: number;
  error?: string;
  trace?: AgentTraceStep[];
};

export type ChatRequest = {
  repo_id: string;
  question: string;
  session_id?: string;
};

export type SseStateEvent = {
  state:
    | "INTAKE"
    | "PLAN"
    | "ACT"
    | "OBSERVE"
    | "DECIDE"
    | "FINALIZE"
    | "VERIFY"
    | "RESPOND";
  label: string;
  timestamp: string;
};

export type DiagramResponse = {
  mermaid: string;
  empty: boolean;
  reason?: "no_connections";
  requested_depth: number;
  clamped: boolean;
  hidden_count?: number;
};

export type EvalHealthResponse = {
  ok: boolean;
  errors: string[];
  details: {
    ready?: boolean;
    sync_status?: string;
    chroma_chunk_count?: number;
    probe_hit_count?: number;
    files_parsed?: number;
    chunks_created?: number;
    job_id?: string;
    asset_repo_id?: string;
    block_message?: string;
    block_reason?: string;
    [key: string]: unknown;
  };
};

export type EvalJobStatus = {
  job_id: string;
  status: "queued" | "running" | "done" | "error";
  started_at?: string;
  result?: EvalRun | GoldenStatus | null;
  error?: string | null;
};

export type RagasScores = Record<string, number>;

export type EvalRun = {
  version: string;
  timestamp?: string;
  git_sha?: string;
  ragas_scores?: RagasScores;
  mean_confidence_score?: number;
  average_iterations?: number;
  invalid_reference_rate?: number;
  retrieval_precision_at_3?: number;
  regression_warning?: string;
  supplementary?: Record<string, number>;
  per_question?: PerQuestionDiagnostic[];
  diagnostics?: {
    question_count?: number;
    gated_count?: number;
    mean_precision_at_3?: number;
  };
};

export type PerQuestionDiagnostic = {
  question: string;
  hit?: boolean;
  precision_at_3?: number;
  gated?: boolean;
  confidence?: number;
  top_files?: string[];
  expected_files?: string[];
};

export type CompareResult = {
  regressions: Array<{
    metric: string;
    baseline_value: number;
    new_value: number;
    delta: number;
    kind: string;
    message: string;
  }>;
  overall_pass: boolean;
  first_run_baseline_established?: boolean;
  baseline_version: string;
  candidate_version: string;
  regressions_found: boolean;
};

export type GoldenStatus = {
  status: string;
  timestamp?: string;
  score?: number;
  total?: number;
  passed?: number;
  pass_threshold?: number;
  failed_questions?: string[];
  per_repo?: Array<{
    fixture: string;
    repo_id: string;
    total: number;
    passed: number;
    score: number;
  }>;
};

export type UsageSummary = {
  org_id: string;
  month: string;
  metrics: Record<string, number>;
  plan_id: string;
  subscription_status: string;
  limits: {
    chat_per_month: number;
    ingest_per_month: number;
    eval_per_month: number;
  };
};

export type SubscriptionStatus = {
  org_id: string;
  plan_id: string;
  status: string;
  plan_name: string;
  limits: {
    chat_per_month: number;
    ingest_per_month: number;
    eval_per_month: number;
  };
  stripe_enabled?: boolean;
};

export type AuditEvent = {
  timestamp: string;
  action: string;
  org_id: string;
  actor: string;
  resource_type: string;
  resource_id: string;
  details: Record<string, unknown>;
};

export type HealthResponse = {
  status: string;
  timestamp?: string;
  version?: string;
};

export type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  gated?: boolean;
  cache_hit?: boolean;
  sources?: ChatSource[];
  trace?: AgentTraceStep[];
  confidence_score?: number;
  elapsed_s?: number;
};

export class ApiError extends Error {
  constructor(
    public statusCode: number,
    message: string,
    public rawResponse = "",
    public retryAfterS: number | null = null,
  ) {
    super(message);
    this.name = "ApiError";
  }
}
