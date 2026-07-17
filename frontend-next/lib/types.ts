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
  truncated_count?: number;
  direction?: string;
  hidden_neighbors?: HiddenNeighbor[];
};

export type HiddenNeighbor = {
  parent_id: string;
  parent_name: string;
  direction: "caller" | "callee";
  id: string;
  name: string;
  path: string;
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
  run_id?: string;
  repo_id?: string;
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
    job_id?: string;
    question_count?: number;
    gated_count?: number;
    mean_precision_at_3?: number;
  };
};

export type PerQuestionDiagnostic = {
  question: string;
  hit?: boolean;
  gt_hit?: boolean;
  precision_at_3?: number;
  gated?: boolean;
  confidence?: number;
  confidence_score?: number;
  top_files?: string[];
  expected_files?: string[];
  ground_truth_files?: string[];
  state_path_consistent?: boolean;
  rate_limited?: boolean;
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
  incomparable?: boolean;
  incomparable_reason?: string;
  index_version_warning?: string;
};

export type GoldenStatus = {
  status: string;
  timestamp?: string;
  score?: number;
  total?: number;
  passed?: number;
  pass_threshold?: number;
  failed_questions?: string[];
  failed_details?: Array<{
    question: string;
    fixture?: string;
    expected_files?: string[];
    cited_files?: string[];
    gated?: boolean;
    error?: string;
  }>;
  skipped_fixtures?: string[];
  age_seconds?: number;
  stale?: boolean;
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
  correlation_id?: string;
};

export type BillingPlan = {
  id: string;
  name: string;
  price_monthly_usd: number;
  limits: {
    chat_per_month: number;
    ingest_per_month: number;
    eval_per_month: number;
  };
};

export type PlatformRepo = {
  repo_id: string;
  asset_repo_id: string;
  repo_url: string;
  ref: string;
  sync_status: string;
  chunks_created: number;
  files_parsed: number;
  commit_hash?: string;
  chroma_chunks?: number;
  index_integrity_ok?: boolean;
};

export type ApiKeySummary = {
  key_prefix: string;
  org_id: string;
  label: string;
  active: boolean;
  created_at?: string;
};

export type CreateApiKeyResponse = {
  api_key: string;
  org_id: string;
  label: string;
};

export type GitHubInstallation = {
  installation_id: number;
  org_id: string;
  account_login?: string;
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
  /** When set, the bubble shows a retry action for the failed user question. */
  retry_question?: string;
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
