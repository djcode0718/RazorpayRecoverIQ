export type OperatingStatus = {
  data_source: "SEEDED DEMO" | "LIVE INGESTION" | string;
  payment_environment: "RAZORPAY TEST" | "SIMULATION" | string;
  ai_provider: "LOCAL" | "EXTERNAL" | "MOCK/FALLBACK" | "UNAVAILABLE" | string;
  ai_provider_note?: string;
  policy_engine: "ACTIVE" | "DEGRADED" | string;
  policy_engine_note?: string;
  webhook: "CONFIGURED" | "WAITING" | "VERIFIED" | "DEGRADED" | string;
  webhook_note?: string;
  api_connectivity?: boolean;
  api_connectivity_reason?: string | null;
  last_event?: string | null;
  last_event_id?: string | null;
  last_event_status?: string | null;
  last_event_received_at?: string | null;
};

export type Summary = {
  mode: string;
  mode_label: string;
  operating_status?: OperatingStatus;
  revenue_at_risk_minor: number;
  recoverable_revenue_minor: number;
  expected_recovery_minor?: number;
  recovery_attempts: number;
  gross_recovered_minor: number;
  net_recovered_minor: number;
  recovery_rate: number;
  active_opportunities: number;
  allowed_actions?: number;
  escalated_actions?: number;
  approved_actions: number;
  blocked_actions: number;
  escalations: number;
  funnel: {
    revenue_at_risk_minor: number;
    ai_identifiable_minor: number;
    policy_eligible_minor: number;
    recovery_attempted_minor: number;
    successfully_recovered_minor: number;
  };
  ai_copilot: {
    active_opportunities_count: number;
    total_recoverable_value_minor: number;
    top_opportunity: {
      id: number;
      customer_reference?: string;
      recommended_action: string;
      confidence: number;
      expected_recovery_minor: number;
    } | null;
  };
};

export type TrendDataPoint = {
  date: string;
  display_date: string;
  revenue_at_risk_minor: number;
  recovered_revenue_minor: number;
  attempts_count: number;
};

export type DashboardEvent = {
  id: number;
  event_type: string;
  actor_type: string;
  entity_type: string;
  entity_id: string;
  result: string | null;
  reason: string | null;
  created_at: string;
};

export type OpportunityListItem = {
  id: number;
  customer_reference: string;
  status: string;
  lifecycle_status: "OPEN" | "RESOLVED" | "CLOSED";
  failure_category: string | null;
  failure_reason: string | null;
  recommended_action: string | null;
  confidence: number;
  recovery_probability: number;
  amount_at_risk_minor: number;
  expected_recovery_minor: number;
  expected_net_recovery_minor: number;
  risk_bucket: string;
  policy_result: string | null;
  latest_attempt_status: string | null;
  latest_verified_outcome: string | null;
  execution_status: "NOT_EXECUTED" | "RUNNING" | "SUCCEEDED" | "FAILED" | string;
  verification_status: "UNVERIFIED" | "PENDING" | "VERIFIED" | "VERIFIED_SUCCESS" | "VERIFIED_FAILURE" | string;
  outcome: "PENDING" | "RECOVERED" | "FAILED" | "EXPIRED" | "BLOCKED" | "ESCALATED" | "NOT_RECOVERED" | string;
  created_at?: string | null;
  updated_at: string | null;
};

export type OpportunityDetail = {
  opportunity: {
    id: number;
    customer_reference?: string;
    status: string;
    lifecycle_status: "OPEN" | "RESOLVED" | "CLOSED";
    failure_category: string | null;
    failure_reason: string | null;
    recommended_action: string | null;
    recovery_probability: number;
    confidence: number;
    currency: string;
    amount_at_risk_minor: number;
    expected_recovery_minor?: number;
    policy_result?: string | null;
    execution_status?: string;
    created_at: string | null;
    updated_at: string | null;
  };
  payment: {
    payment_id: number;
    razorpay_payment_id: string | null;
    razorpay_order_id: string | null;
    status: string;
    captured: boolean;
    method: string | null;
    amount_minor: number;
    currency: string;
    failure_reason: string | null;
    failure_code: string | null;
  } | null;
  customer_history: {
    customer_id: number | null;
    segment: string | null;
    total_attempts: number;
    successful_count: number;
    failed_count: number;
    historical_recovery_count: number | null;
  };
  failure: {
    category: string | null;
    reason: string | null;
    payment_failure_reason: string | null;
    payment_failure_code: string | null;
  };
  evidence: {
    diagnosis: string | null;
    model_evidence: Record<string, unknown>;
    decision_source: string | null;
    provider: string | null;
    model: string | null;
    schema_version: string | null;
  };
  economics: {
    expected_recovery_minor: number;
    estimated_intervention_cost_minor: number;
    expected_net_recovery_minor: number;
    gross_recovered_minor: number;
    net_recovered_minor: number;
    total_intervention_cost_minor: number;
  };
  policy_checks: {
    result: string | null;
    checks: Record<string, boolean>;
    reason_codes: { failed: string[]; passed: string[] };
    policy_version: string | null;
    evaluated_at?: string | null;
  };
  action_traceability: {
    recommended_action: string | null;
    allow_execution: boolean | null;
    latest_attempt_status: string | null;
    latest_verified_outcome: string | null;
    attempt_count: number;
    execution_status: "NOT_EXECUTED" | "RUNNING" | "SUCCEEDED" | "FAILED" | string;
    verification_status: "UNVERIFIED" | "PENDING" | "VERIFIED" | "VERIFIED_SUCCESS" | "VERIFIED_FAILURE" | string;
    outcome: "PENDING" | "RECOVERED" | "FAILED" | "EXPIRED" | "BLOCKED" | "ESCALATED" | "NOT_RECOVERED" | string;
    execution_mode: string;
  };
  semantic_states?: {
    original_payment: string | null;
    opportunity: string | null;
    ai: string | null;
    recommendation: string | null;
    policy: string | null;
    attempt: string | null;
    payment_link: string | null;
    recovery_payment: string | null;
    verification: string | null;
    business_outcome: string | null;
  };
  recovery_state: {
    current: string;
    stages: Array<{ name: string; reached: boolean }>;
  };
  attempts: Array<{
    attempt_number: number;
    action: string;
    status: string;
    verified_outcome: string | null;
    amount_minor: number;
    recovered_amount_minor: number;
    requested_at: string | null;
    executed_at: string | null;
    completed_at: string | null;
    payment_link: {
      payment_link_id: string;
      payment_link_reference_id: string;
      status: string;
      amount_minor?: number;
      short_url?: string | null;
    } | null;
  }>;
  audit_trail?: Array<{
    id?: number;
    event_type: string;
    stage?: string | null;
    actor_id?: string | null;
    created_at?: string | null;
    details?: Record<string, unknown>;
  }>;
  timeline: Array<{
    timestamp: string | null;
    event_type: string;
    stage: string | null;
    stage_group: string;
    outcome_status: "pass" | "fail" | "pending";
    actor_type: string;
    reason: string | null;
    outcome: Record<string, unknown> | null;
  }>;
  ai_validation?: {
    provider_available: boolean;
    valid_schema: boolean;
    rejected: boolean;
    fallback_used: boolean;
    reason: string | null;
  };
  decision_explanation?: {
    signals: Array<{ label: string; passed: boolean }>;
    constraints: Array<{ label: string; passed: boolean }>;
  };
};

export type RazorpayStatusResponse = {
  success: boolean;
  data?: {
    test_mode: boolean;
    adapter_mode?: string;
    live_mode_detected: boolean;
    credentials_configured: boolean;
    api_connectivity: boolean;
    api_connectivity_reason: string | null;
    webhook_configured: boolean;
    operating_status?: OperatingStatus;
    last_event?: string | null;
    last_event_id?: string | null;
    last_event_status?: string | null;
    last_event_received_at?: string | null;
    last_successful_razorpay_operation?: {
      operation: string;
      payment_link_id: string;
      reference_id: string;
      short_url: string | null;
      status: string;
      updated_at: string | null;
    } | null;
  };
  error?: { code?: string; message?: string };
};

export type SummaryResponse = {
  success: boolean;
  data?: Summary;
  error?: { code?: string; message?: string };
};

export type OpportunityListResponse = {
  success: boolean;
  data?: {
    items: OpportunityListItem[];
    count: number;
    page: number;
    page_size: number;
    total_count: number;
    total_pages: number;
    has_next: boolean;
    has_prev: boolean;
  };
  error?: { code?: string; message?: string };
};

export type OpportunityDetailResponse = {
  success: boolean;
  data?: OpportunityDetail;
  error?: { code?: string; message?: string };
};

export type EvaluationSummary = {
  evaluation_run_id: string;
  records: number;
  precision: number;
  recall: number;
  f1: number;
  false_positive_rate: number;
  revenue_at_risk_minor: number;
  recoverable_revenue_minor: number;
  gross_recovered_minor: number;
  intervention_cost_minor: number;
  net_recovered_minor: number;
  recovery_rate: number;
  false_positive_count: number;
  false_positive_exposure_minor: number;
  false_positive_intervention_cost_minor: number;
  operational?: {
    allowed: number;
    blocked: number;
    escalated: number;
    failed: number;
  };
  last_created_at?: string | null;
};

export type EvaluationRunResponse = {
  success: boolean;
  data?: EvaluationSummary;
  error?: { code?: string; message?: string };
};

export type EvaluationHistoryResponse = {
  success: boolean;
  data?: { items: EvaluationSummary[]; count: number };
  error?: { code?: string; message?: string };
};

export type EvaluationComparisonResponse = {
  success: boolean;
  data?: {
    baseline: EvaluationSummary;
    recoveriq: EvaluationSummary;
    deltas: {
      precision_delta: number;
      recall_delta: number;
      f1_delta: number;
      false_positive_rate_delta: number;
      recovery_rate_delta: number;
      net_recovered_minor_delta: number;
      false_positive_count_delta: number;
      false_positive_exposure_minor_delta: number;
      false_positive_intervention_cost_minor_delta: number;
      allowed_delta: number;
      blocked_delta: number;
      escalated_delta: number;
      failed_delta: number;
    };
    attribution: {
      baseline: {
        action_counts: Record<string, number>;
        policy_reason_counts: Record<string, number>;
      };
      recoveriq: {
        action_counts: Record<string, number>;
        policy_reason_counts: Record<string, number>;
      };
      action_level_deltas: Record<string, number>;
      policy_reason_deltas: Record<string, number>;
    };
    comparison_note: string;
    metadata?: {
      dataset_version: string;
      split: string;
      generation_seed: number | null;
      total_cases: number;
      model_strategy: string;
      run_id: string;
      timestamp: string | null;
      reproducible: boolean;
    };
  };
  error?: { code?: string; message?: string };
};

export type EvaluationDrilldownResponse = {
  success: boolean;
  data?: {
    summary: EvaluationSummary;
    confusion_matrix: { tp: number; fp: number; fn: number; tn: number };
    false_positive_cost: {
      count: number;
      financial_exposure_minor: number;
      intervention_cost_minor: number;
    };
    operational: {
      allowed: number;
      blocked: number;
      escalated: number;
      failed: number;
    };
    metric_drilldown: {
      failed_payment_accuracy: number;
      successful_payment_accuracy: number;
      total_errors: number;
    };
    sample_errors: Array<{
      case_id: number;
      error_type: string;
      predicted_action: string;
      actual_action: string;
      failure_reason: string | null;
    }>;
  };
  error?: { code?: string; message?: string };
};

export type FailureScenario = {
  scenario_id: string;
  title: string;
  severity: string;
  expected_error_code: string;
  description: string;
  expected_behavior?: string;
  actual_behavior?: string;
  trigger?: string;
  system_outcome?: string;
  audit_result?: string;
  error_code?: string;
  error_message?: string;
  state_transitions?: Record<string, string>;
};

export type FailureScenariosResponse = {
  success: boolean;
  data?: { scenarios: FailureScenario[] };
  error?: { code?: string; message?: string };
};

export type ReadinessCheck = {
  id: string;
  status: "PASS" | "PARTIAL" | "FAIL" | string;
  message: string;
  evidence: Record<string, unknown>;
};

export type ReadinessValidationData = {
  workflow: string;
  status: "PASS" | "PARTIAL" | "FAIL" | "READY" | "BLOCKED" | string;
  release_gate?: "READY" | "PARTIAL" | "BLOCKED" | string;
  gate_reason?: string;
  checks: ReadinessCheck[];
  summary: {
    pass_count: number;
    partial_count: number;
    fail_count: number;
  };
  readiness_score?: number;
  recommended_next_step?: string;
};

export type Tone = "good" | "warn" | "bad" | "info" | "neutral";

export type HealthItem = {
  label: string;
  healthy: boolean;
  statusText?: string;
  note: string;
};
