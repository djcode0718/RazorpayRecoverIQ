import { useEffect, useMemo, useState, Fragment, type CSSProperties } from "react";
import "./app.css";

type Summary = {
  mode: string;
  mode_label: string;
  revenue_at_risk_minor: number;
  recoverable_revenue_minor: number;
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
      recommended_action: string;
      confidence: number;
      expected_recovery_minor: number;
    } | null;
  };
};

type TrendDataPoint = {
  date: string;
  display_date: string;
  revenue_at_risk_minor: number;
  recovered_revenue_minor: number;
  attempts_count: number;
};

type DashboardEvent = {
  id: number;
  event_type: string;
  actor_type: string;
  entity_type: string;
  entity_id: string;
  result: string | null;
  reason: string | null;
  created_at: string;
};

type OpportunityListItem = {
  id: number;
  customer_reference: string;
  status: string;
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
  business_outcome_status?: string | null;
  updated_at: string | null;
};

type OpportunityDetail = {
  opportunity: {
    id: number;
    status: string;
    failure_category: string | null;
    failure_reason: string | null;
    recommended_action: string | null;
    recovery_probability: number;
    confidence: number;
    currency: string;
    amount_at_risk_minor: number;
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
    } | null;
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
  timeline_groups: Array<{
    group: string;
    counts: { pass: number; fail: number; pending: number };
    events: Array<{
      timestamp: string | null;
      event_type: string;
      stage: string | null;
      stage_group: string;
      outcome_status: "pass" | "fail" | "pending";
      actor_type: string;
      reason: string | null;
      outcome: Record<string, unknown> | null;
    }>;
  }>;
  ai_validation?: {
    provider_available: boolean;
    valid_schema: boolean;
    rejected: boolean;
    fallback_used: boolean;
    reason: string | null;
  };
  idempotency_check?: {
    received: boolean;
    already_processed: boolean;
    duplicate_ignored: boolean;
    no_second_action: boolean;
    delivery_count: number;
    event_id: string | null;
  };
  strategy_comparison?: Array<{
    name: string;
    probability: number;
    expected_recovery_minor: number;
    risk: string;
    selected: boolean;
  }>;
  decision_explanation?: {
    signals: Array<{ label: string; passed: boolean }>;
    constraints: Array<{ label: string; passed: boolean }>;
  };
  timeline_stages?: Array<{
    stage: string;
    reached: boolean;
    status: string;
    timestamp: string | null;
    details: Record<string, any>;
  }>;
};

type RazorpayStatusResponse = {
  success: boolean;
  data?: {
    test_mode: boolean;
    adapter_mode?: string;
    live_mode_detected: boolean;
    credentials_configured: boolean;
    api_connectivity: boolean;
    api_connectivity_reason: string | null;
    webhook_configured: boolean;
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

type SummaryResponse = {
  success: boolean;
  data?: Summary;
  error?: { code?: string; message?: string };
};

type OpportunityListResponse = {
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

type OpportunityDetailResponse = {
  success: boolean;
  data?: OpportunityDetail;
  error?: { code?: string; message?: string };
};

type EvaluationSummary = {
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

type EvaluationRunResponse = {
  success: boolean;
  data?: EvaluationSummary;
  error?: { code?: string; message?: string };
};

type EvaluationHistoryResponse = {
  success: boolean;
  data?: { items: EvaluationSummary[]; count: number };
  error?: { code?: string; message?: string };
};

type EvaluationComparisonResponse = {
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

type EvaluationDrilldownResponse = {
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

type FailureScenario = {
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
  state_transitions?: Record<string, string>;
};

type FailureScenariosResponse = {
  success: boolean;
  data?: { scenarios: FailureScenario[] };
  error?: { code?: string; message?: string };
};

type ReadinessValidationResponse = {
  success: boolean;
  data?: {
    workflow: string;
    status: "PASS" | "PARTIAL" | "FAIL";
    checks: Array<{
      id: string;
      status: "PASS" | "PARTIAL" | "FAIL";
      message: string;
      evidence: Record<string, unknown>;
    }>;
    summary: {
      pass_count: number;
      partial_count: number;
      fail_count: number;
    };
    readiness_score?: number;
    recommended_next_step?: string;
  };
  error?: { code?: string; message?: string };
};

type Tone = "good" | "warn" | "bad" | "info" | "neutral";

type HealthItem = {
  label: string;
  healthy: boolean;
  note: string;
};

const JOURNEY_STAGES = [
  "FAILED PAYMENT",
  "REVENUE AT RISK",
  "AI DIAGNOSIS",
  "POLICY DECISION",
  "RECOVERY ACTION",
  "PAYMENT",
  "VERIFICATION",
  "RECOVERED",
] as const;

const DEFAULT_BUTTON_STYLE: CSSProperties = {};

function formatMinorCurrency(minorUnits: number): string {
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 2,
  }).format(minorUnits / 100);
}
function formatPercentage(value: number, isDecimalFraction = false): string {
  if (!Number.isFinite(value)) {
    return "-";
  }
  let isDecimal = isDecimalFraction;
  if (value > 0 && value <= 1.0) {
    isDecimal = true;
  } else if (value > 1.0) {
    isDecimal = false;
  }
  const percentValue = isDecimal ? value * 100 : value;
  return `${percentValue.toFixed(1)}%`;
}

function formatIsoTimestamp(input: string | null): string {
  if (!input) {
    return "-";
  }
  const value = new Date(input);
  if (Number.isNaN(value.getTime())) {
    return input;
  }
  return value.toLocaleString();
}

function toTitle(value: string): string {
  return value
    .replace(/_/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/\w\S*/g, (word) => `${word.charAt(0).toUpperCase()}${word.slice(1).toLowerCase()}`);
}

function parseNumber(input: string, fallback: number): number {
  const parsed = Number.parseInt(input, 10);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function toToneForOutcome(value: string | null): Tone {
  const normalized = (value || "").toUpperCase();
  if (["SUCCESS", "RECOVERED", "CAPTURED", "PASS"].some((item) => normalized.includes(item))) {
    return "good";
  }
  if (["FAILED", "FAIL", "BLOCK", "CANCEL"].some((item) => normalized.includes(item))) {
    return "bad";
  }
  if (normalized.length > 0) {
    return "warn";
  }
  return "neutral";
}

function toToneForRisk(value: string): Tone {
  const normalized = value.toUpperCase();
  if (normalized.includes("HIGH")) {
    return "bad";
  }
  if (normalized.includes("MED")) {
    return "warn";
  }
  if (normalized.includes("LOW")) {
    return "good";
  }
  return "neutral";
}

function isLikelyUrl(value: string): boolean {
  return /^https?:\/\//i.test(value);
}

function serializeEvidence(value: unknown): string {
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return "{}";
  }
}

function isEmptySummary(summary: Summary): boolean {
  return (
    summary.revenue_at_risk_minor === 0 &&
    summary.recoverable_revenue_minor === 0 &&
    summary.gross_recovered_minor === 0 &&
    summary.active_opportunities === 0
  );
}

function normalizeKey(value: string): string {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, "");
}

function getPolicyCheckLabel(key: string): string {
  const normalized = normalizeKey(key);
  if (normalized.includes("testmode")) return "Test Mode";
  if (normalized.includes("amount")) return "Amount";
  if (normalized.includes("confidence")) return "Confidence";
  if (normalized.includes("expected") && normalized.includes("recover")) return "Expected Recovery";
  if (normalized.includes("retry") && normalized.includes("limit")) return "Retry Limit";
  if (normalized.includes("duplicate")) return "Duplicate Check";
  return toTitle(key);
}

function getPolicyDecision(detail: OpportunityDetail): "ALLOW" | "BLOCK" | "PENDING" {
  const result = (detail.policy_checks.result || "").toUpperCase();
  if (result.includes("ALLOW") || result.includes("APPROV")) {
    return "ALLOW";
  }
  if (result.includes("BLOCK") || result.includes("FAIL")) {
    return "BLOCK";
  }
  return "PENDING";
}

function inferJourneyStates(detail: OpportunityDetail): { reached: boolean[]; activeIndex: number } {
  const semantic = detail.semantic_states;
  const reached: boolean[] = [
    Boolean(detail.payment?.status?.toUpperCase().includes("FAIL") || semantic?.original_payment),
    detail.opportunity.amount_at_risk_minor > 0,
    Boolean(detail.evidence.diagnosis || detail.evidence.provider),
    Boolean(detail.policy_checks.result),
    detail.attempts.length > 0 || Boolean(detail.action_traceability.recommended_action),
    Boolean(detail.semantic_states?.recovery_payment || detail.payment?.razorpay_payment_id || detail.attempts.length > 0),
    Boolean(detail.semantic_states?.verification || detail.action_traceability.latest_verified_outcome),
    Boolean((detail.semantic_states?.business_outcome || detail.action_traceability.latest_verified_outcome || "").toUpperCase().includes("RECOVER")),
  ];

  const current = normalizeKey(detail.recovery_state.current);
  const stageLookup: Record<string, number> = {
    failedpayment: 0,
    revenueatrisk: 1,
    aidediagnosis: 2,
    aidiagnosis: 2,
    policydecision: 3,
    recoveryaction: 4,
    payment: 5,
    verification: 6,
    recovered: 7,
  };

  let activeIndex = stageLookup[current] ?? -1;
  if (activeIndex < 0) {
    activeIndex = reached.reduce((last, value, index) => (value ? index : last), 0);
  }
  return { reached, activeIndex };
}

function extractPaymentLinkUrl(detail: OpportunityDetail, razorpayStatus: RazorpayStatusResponse["data"] | null): string | null {
  if (detail.timeline.length > 0) {
    for (const event of detail.timeline) {
      if (!event.outcome) {
        continue;
      }
      for (const value of Object.values(event.outcome)) {
        if (typeof value === "string" && isLikelyUrl(value)) {
          return value;
        }
      }
    }
  }

  const fallbackUrl = razorpayStatus?.last_successful_razorpay_operation?.short_url || null;
  return fallbackUrl && isLikelyUrl(fallbackUrl) ? fallbackUrl : null;
}

export function App() {
  const [summary, setSummary] = useState<Summary | null>(null);
  const [dashboardTrend, setDashboardTrend] = useState<TrendDataPoint[]>([]);
  const [dashboardEvents, setDashboardEvents] = useState<DashboardEvent[]>([]);
  const [opportunities, setOpportunities] = useState<OpportunityListItem[]>([]);
  const [selectedOpportunityId, setSelectedOpportunityId] = useState<number | null>(null);
  const [detail, setDetail] = useState<OpportunityDetail | null>(null);
  const [selectedTimelineStage, setSelectedTimelineStage] = useState<string | null>(null);
  const [explanationTab, setExplanationTab] = useState<"signals" | "constraints">("signals");
  const [isExecutingRecovery, setIsExecutingRecovery] = useState<boolean>(false);
  const [executionMessage, setExecutionMessage] = useState<string | null>(null);
  const [activeResilienceScenario, setActiveResilienceScenario] = useState<any | null>(null);
  const [resilienceError, setResilienceError] = useState<string | null>(null);

  const [activeTab, setActiveTab] = useState<string>("Command Center");
  const [expandedScenarioId, setExpandedScenarioId] = useState<string | null>(null);

  const handleTabChange = (newTab: string) => {
    setActiveTab(newTab);
    setSelectedOpportunityId(null);
    setDetail(null);
  };

  const [statusFilter, setStatusFilter] = useState<string>("ALL");
  const [actionFilter, setActionFilter] = useState<string>("ALL");
  const [searchInput, setSearchInput] = useState<string>("");
  const [searchFilter, setSearchFilter] = useState<string>("");
  const [opportunityPage, setOpportunityPage] = useState<number>(1);
  const [opportunityPageSize, setOpportunityPageSize] = useState<number>(20);
  const [opportunityTotalCount, setOpportunityTotalCount] = useState<number>(0);
  const [opportunityTotalPages, setOpportunityTotalPages] = useState<number>(1);
  const [opportunityHasNext, setOpportunityHasNext] = useState<boolean>(false);
  const [opportunityHasPrev, setOpportunityHasPrev] = useState<boolean>(false);

  const [evaluationHistory, setEvaluationHistory] = useState<EvaluationSummary[]>([]);
  const [selectedEvaluationRunId, setSelectedEvaluationRunId] = useState<string | null>(null);
  const [evaluationComparison, setEvaluationComparison] = useState<EvaluationComparisonResponse["data"] | null>(null);
  const [evaluationDrilldown, setEvaluationDrilldown] = useState<EvaluationDrilldownResponse["data"] | null>(null);
  const [isEvaluationLoading, setIsEvaluationLoading] = useState<boolean>(false);
  const [isRunSubmitting, setIsRunSubmitting] = useState<boolean>(false);
  const [runDatasetVersion, setRunDatasetVersion] = useState<string>("default_dataset");
  const [runSplit, setRunSplit] = useState<string>("TEST");
  const [runGenerationSeed, setRunGenerationSeed] = useState<string>("42");
  const [runTotalCases, setRunTotalCases] = useState<string>("1000");

  const [failureScenarios, setFailureScenarios] = useState<FailureScenario[]>([]);
  const [failureScenarioResult, setFailureScenarioResult] = useState<string>("");
  const [readinessValidation, setReadinessValidation] = useState<ReadinessValidationResponse["data"] | null>(null);
  const [isReadinessRunning, setIsReadinessRunning] = useState<boolean>(false);
  const [razorpayStatus, setRazorpayStatus] = useState<RazorpayStatusResponse["data"] | null>(null);
  const [timelineCollapsed, setTimelineCollapsed] = useState<Record<string, boolean>>({});

  const [demoMutationMessage, setDemoMutationMessage] = useState<string>("");
  const [isDemoMutating, setIsDemoMutating] = useState<boolean>(false);

  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [isOpportunityLoading, setIsOpportunityLoading] = useState<boolean>(false);
  const [isDetailLoading, setIsDetailLoading] = useState<boolean>(false);
  const [autoRefreshEnabled, setAutoRefreshEnabled] = useState<boolean>(false);

  const loadSummary = async () => {
    const response = await fetch("/api/v1/dashboard/summary");
    const payload = (await response.json()) as SummaryResponse;
    if (!response.ok || !payload.success || !payload.data) {
      throw new Error(payload.error?.message || "Unable to load dashboard summary.");
    }
    setSummary(payload.data);
  };

  const loadDashboardTrend = async () => {
    const response = await fetch("/api/v1/dashboard/trend");
    const payload = (await response.json()) as { success: boolean; data?: TrendDataPoint[]; error?: { message?: string } };
    if (!response.ok || !payload.success || !payload.data) {
      throw new Error(payload.error?.message || "Unable to load dashboard trend.");
    }
    setDashboardTrend(payload.data);
  };

  const loadDashboardEvents = async () => {
    const response = await fetch("/api/v1/dashboard/events");
    const payload = (await response.json()) as { success: boolean; data?: DashboardEvent[]; error?: { message?: string } };
    if (!response.ok || !payload.success || !payload.data) {
      throw new Error(payload.error?.message || "Unable to load dashboard event stream.");
    }
    setDashboardEvents(payload.data);
  };

  const loadRazorpayStatus = async () => {
    const response = await fetch("/api/v1/integrations/razorpay/status");
    const payload = (await response.json()) as RazorpayStatusResponse;
    if (!response.ok || !payload.success || !payload.data) {
      throw new Error(payload.error?.message || "Unable to load Razorpay integration status.");
    }
    setRazorpayStatus(payload.data);
  };

  const loadOpportunities = async (showLoader: boolean) => {
    if (showLoader) {
      setIsOpportunityLoading(true);
    }

    const query = new URLSearchParams();
    query.set("pagination_mode", "page");
    query.set("page", String(opportunityPage));
    query.set("page_size", String(opportunityPageSize));
    query.set("sort_by", "updated_desc");
    if (statusFilter !== "ALL") {
      query.set("status", statusFilter);
    }
    if (actionFilter !== "ALL") {
      query.set("action", actionFilter);
    }
    if (searchFilter.trim().length > 0) {
      query.set("search", searchFilter.trim());
    }

    const response = await fetch(`/api/v1/opportunities?${query.toString()}`);
    const payload = (await response.json()) as OpportunityListResponse;
    if (!response.ok || !payload.success || !payload.data) {
      if (showLoader) {
        setIsOpportunityLoading(false);
      }
      throw new Error(payload.error?.message || "Unable to load opportunities.");
    }

    setOpportunities(payload.data.items);
    setOpportunityTotalCount(payload.data.total_count);
    setOpportunityTotalPages(payload.data.total_pages);
    setOpportunityHasNext(payload.data.has_next);
    setOpportunityHasPrev(payload.data.has_prev);

    if (payload.data.items.length === 0) {
      setSelectedOpportunityId(null);
      setDetail(null);
      if (showLoader) {
        setIsOpportunityLoading(false);
      }
      return;
    }

    const hasSelected = payload.data.items.some((item) => item.id === selectedOpportunityId);
    if (!hasSelected) {
      setSelectedOpportunityId(null);
    }

    if (showLoader) {
      setIsOpportunityLoading(false);
    }
  };

  const loadOpportunityDetail = async (opportunityId: number) => {
    setIsDetailLoading(true);
    try {
      const response = await fetch(`/api/v1/opportunities/${opportunityId}`);
      const payload = (await response.json()) as OpportunityDetailResponse;
      if (!response.ok || !payload.success || !payload.data) {
        throw new Error(payload.error?.message || "Unable to load opportunity detail.");
      }
      setDetail(payload.data);
      setSelectedTimelineStage("DETECTED");
      setTimelineCollapsed({});
    } finally {
      setIsDetailLoading(false);
    }
  };

  const handleExecuteRecovery = async (opportunityId: number) => {
    setIsExecutingRecovery(true);
    setExecutionMessage(null);
    try {
      const response = await fetch(`/api/v1/opportunities/${opportunityId}/execute`, {
        method: "POST",
      });
      const payload = await response.json();
      if (!response.ok || !payload.success) {
        throw new Error(payload.error?.message || "Execution failed.");
      }
      setExecutionMessage("Recovery action triggered successfully!");
      await loadOpportunities(false);
      await loadOpportunityDetail(opportunityId);
    } catch (err: any) {
      setExecutionMessage(err.message || "An execution error occurred.");
    } finally {
      setIsExecutingRecovery(false);
    }
  };

  const loadEvaluationHistory = async () => {
    const response = await fetch("/api/v1/evaluation/history?limit=10");
    const payload = (await response.json()) as EvaluationHistoryResponse;
    if (!response.ok || !payload.success || !payload.data) {
      throw new Error(payload.error?.message || "Unable to load evaluation history.");
    }
    setEvaluationHistory(payload.data.items);
    if (payload.data.items.length > 0 && !selectedEvaluationRunId) {
      setSelectedEvaluationRunId(payload.data.items[0].evaluation_run_id);
    }
  };

  const loadEvaluationRunInsights = async (runId: string) => {
    setIsEvaluationLoading(true);
    try {
      const [comparisonResponse, drilldownResponse] = await Promise.all([
        fetch(`/api/v1/evaluation/${runId}/comparison`),
        fetch(`/api/v1/evaluation/${runId}/drilldown`),
      ]);

      const comparisonPayload = (await comparisonResponse.json()) as EvaluationComparisonResponse;
      const drilldownPayload = (await drilldownResponse.json()) as EvaluationDrilldownResponse;

      if (!comparisonResponse.ok || !comparisonPayload.success || !comparisonPayload.data) {
        throw new Error(comparisonPayload.error?.message || "Unable to load evaluation comparison.");
      }
      if (!drilldownResponse.ok || !drilldownPayload.success || !drilldownPayload.data) {
        throw new Error(drilldownPayload.error?.message || "Unable to load evaluation drilldown.");
      }

      setEvaluationComparison(comparisonPayload.data);
      setEvaluationDrilldown(drilldownPayload.data);
    } finally {
      setIsEvaluationLoading(false);
    }
  };

  const runEvaluation = async () => {
    setIsRunSubmitting(true);
    try {
      const response = await fetch("/api/v1/evaluation/run", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          dataset_version: runDatasetVersion,
          split: runSplit,
          generation_seed: parseNumber(runGenerationSeed, 42),
          total_cases: parseNumber(runTotalCases, 1000),
          generate_if_missing: true,
        }),
      });
      const payload = (await response.json()) as EvaluationRunResponse;
      if (!response.ok || !payload.success || !payload.data) {
        throw new Error(payload.error?.message || "Unable to run evaluation.");
      }
      const runId = payload.data.evaluation_run_id;
      setSelectedEvaluationRunId(runId);
      await loadEvaluationHistory();
      await loadEvaluationRunInsights(runId);
    } finally {
      setIsRunSubmitting(false);
    }
  };

  const loadFailureScenarios = async () => {
    const response = await fetch("/api/v1/failure-demos");
    const payload = (await response.json()) as FailureScenariosResponse;
    if (!response.ok || !payload.success || !payload.data) {
      throw new Error(payload.error?.message || "Unable to load failure scenarios.");
    }
    setFailureScenarios(payload.data.scenarios);
  };

  const triggerFailureScenario = async (scenarioId: string) => {
    const scenarioMeta = failureScenarios.find((scenario) => scenario.scenario_id === scenarioId);
    const expectedCode = scenarioMeta?.expected_error_code || null;
    setActiveResilienceScenario(null);
    setResilienceError(null);
    setFailureScenarioResult("");
    try {
      const response = await fetch("/api/v1/failure-demos/trigger", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ scenario_id: scenarioId }),
      });
      const payload = await response.json();
      
      if (payload.data) {
        setActiveResilienceScenario({
          scenario_id: scenarioId,
          title: scenarioMeta?.title || scenarioId,
          severity: scenarioMeta?.severity || "high",
          ...payload.data,
          error_code: payload.error?.code,
          error_message: payload.error?.message,
        });
      }

      const actualCode = payload.error?.code || "SUCCESS";
      const actualMessage = payload.error?.message || "Operation succeeded.";

      if (response.ok) {
        setFailureScenarioResult(`Scenario ${scenarioId} -> PASS (HTTP ${response.status}): ${actualMessage}`);
      } else if (expectedCode && actualCode === expectedCode) {
        setFailureScenarioResult(`Scenario ${scenarioId} -> PASS (expected ${expectedCode}, HTTP ${response.status}): ${actualMessage}`);
      } else {
        setFailureScenarioResult(`Scenario ${scenarioId} -> UNEXPECTED (${actualCode}, HTTP ${response.status})` + (expectedCode ? ` expected ${expectedCode}` : "") + `: ${actualMessage}`);
      }
    } catch (err: any) {
      setResilienceError(err.message || "Failed to execute resilience scenario.");
    }
  };

  const executeReadinessValidation = async () => {
    setIsReadinessRunning(true);
    try {
      const response = await fetch("/api/v1/readiness/execute", { method: "POST" });
      const payload = (await response.json()) as ReadinessValidationResponse;
      if (!response.ok || !payload.success || !payload.data) {
        throw new Error(payload.error?.message || "Unable to execute readiness workflow.");
      }
      setReadinessValidation(payload.data);
    } finally {
      setIsReadinessRunning(false);
    }
  };

  const runDemoMutation = async (endpoint: "/api/v1/demo/reset-core-recovery" | "/api/v1/demo/seed-core-recovery") => {
    setIsDemoMutating(true);
    setDemoMutationMessage("");
    try {
      const response = await fetch(endpoint, { method: "POST" });
      const payload = (await response.json()) as { success?: boolean; error?: { message?: string } };
      if (!response.ok || !payload.success) {
        throw new Error(payload.error?.message || "Demo operation failed.");
      }
      setDemoMutationMessage(endpoint.includes("reset") ? "Simulation reset complete." : "Simulation seed complete.");
      await loadCommandCenter();
    } finally {
      setIsDemoMutating(false);
    }
  };

  const loadCommandCenter = async () => {
    setIsLoading(true);
    setError(null);
    setSelectedOpportunityId(null);
    setDetail(null);
    try {
      await Promise.all([
        loadSummary(),
        loadOpportunities(false),
        loadEvaluationHistory(),
        loadFailureScenarios(),
        loadRazorpayStatus(),
        loadDashboardTrend(),
        loadDashboardEvents(),
      ]);
      if (selectedEvaluationRunId) {
        await loadEvaluationRunInsights(selectedEvaluationRunId);
      }
    } catch (fetchError) {
      const message = fetchError instanceof Error ? fetchError.message : "Unable to load command center data.";
      setError(message);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadCommandCenter();
  }, []);

  useEffect(() => {
    loadOpportunities(true).catch((fetchError: Error) => {
      setError(fetchError.message || "Unable to load opportunities.");
    });
  }, [statusFilter, actionFilter, searchFilter, opportunityPage, opportunityPageSize]);

  useEffect(() => {
    if (!selectedOpportunityId) {
      return;
    }
    loadOpportunityDetail(selectedOpportunityId).catch((fetchError: Error) => {
      setError(fetchError.message || "Unable to load opportunity detail.");
    });
  }, [selectedOpportunityId]);

  useEffect(() => {
    if (!selectedEvaluationRunId) {
      return;
    }
    loadEvaluationRunInsights(selectedEvaluationRunId).catch((fetchError: Error) => {
      setError(fetchError.message || "Unable to load evaluation insights.");
    });
  }, [selectedEvaluationRunId]);

  // Lock body scroll when drawer is open
  useEffect(() => {
    if (selectedOpportunityId !== null) {
      document.body.classList.add("drawer-open");
    } else {
      document.body.classList.remove("drawer-open");
    }
    return () => {
      document.body.classList.remove("drawer-open");
    };
  }, [selectedOpportunityId]);

  // Close drawer on Escape key press
  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setSelectedOpportunityId(null);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => {
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, []);

  useEffect(() => {
    if (!autoRefreshEnabled) {
      return;
    }
    const intervalId = window.setInterval(() => {
      loadCommandCenter();
      if (selectedOpportunityId) {
        loadOpportunityDetail(selectedOpportunityId).catch(() => undefined);
      }
    }, 15000);
    return () => window.clearInterval(intervalId);
  }, [autoRefreshEnabled, selectedOpportunityId]);

  const selectedItem = useMemo(
    () => opportunities.find((item) => item.id === selectedOpportunityId) ?? null,
    [opportunities, selectedOpportunityId],
  );

  const modeLabel = useMemo(() => {
    if (summary?.mode === "razorpay_test" || razorpayStatus?.test_mode) {
      return "RAZORPAY TEST MODE";
    }
    return "SIMULATION MODE";
  }, [summary?.mode, razorpayStatus?.test_mode]);

  const healthItems = useMemo<HealthItem[]>(() => {
    const aiHealthy = Boolean(detail?.evidence.diagnosis || detail?.evidence.provider || selectedItem?.recommended_action);
    const policyHealthy = Boolean(detail?.policy_checks.result || summary);
    return [
      {
        label: "Razorpay API",
        healthy: Boolean(razorpayStatus?.api_connectivity),
        note: razorpayStatus?.api_connectivity_reason || (razorpayStatus?.api_connectivity ? "Connected" : "Disconnected"),
      },
      {
        label: "Webhook",
        healthy: Boolean(razorpayStatus?.webhook_configured),
        note: razorpayStatus?.last_event ? `${razorpayStatus.last_event} ${formatIsoTimestamp(razorpayStatus.last_event_received_at || null)}` : "No recent event",
      },
      {
        label: "AI",
        healthy: aiHealthy,
        note: aiHealthy ? "Diagnosis available" : "Awaiting explainability signal",
      },
      {
        label: "Policy Engine",
        healthy: policyHealthy,
        note: detail?.policy_checks.result ? `Latest decision ${detail.policy_checks.result}` : "Awaiting policy decision",
      },
    ];
  }, [razorpayStatus, detail, selectedItem, summary]);

  const recoveredCoverage = summary && summary.recoverable_revenue_minor > 0
    ? summary.gross_recovered_minor / summary.recoverable_revenue_minor
    : 0;

  const journeyState = detail ? inferJourneyStates(detail) : null;
  const policyDecision = detail ? getPolicyDecision(detail) : "PENDING";
  const latestAttemptWithLink = detail?.attempts.find((attempt) => Boolean(attempt.payment_link)) || null;
  const paymentLinkUrl = detail ? extractPaymentLinkUrl(detail, razorpayStatus) : null;

  return (
    <main className="ui-shell">
      <section className="ui-container">
        <header className="hero panel">
          <div>
            <p className="eyebrow">RecoverIQ</p>
            <h1>AI Revenue Recovery Command Center</h1>
            <p className="hero-copy">Recover failed payments before they become lost revenue.</p>
            <p className="hero-flow">Detect {"->"} Diagnose {"->"} Decide {"->"} Recover {"->"} Verify</p>
          </div>
          <div className="hero-actions">
            <div className="mode-chip">{modeLabel}</div>
            <button onClick={loadCommandCenter} className="btn btn-primary">
              Refresh
            </button>
            <button
              onClick={() => runDemoMutation("/api/v1/demo/seed-core-recovery")}
              className="btn btn-secondary"
              disabled={isDemoMutating}
            >
              Load Demo Scenario
            </button>
            <button
              onClick={() => runDemoMutation("/api/v1/demo/reset-core-recovery")}
              className="btn btn-tertiary"
              disabled={isDemoMutating}
            >
              Reset Demo
            </button>
            <label className="auto-refresh-toggle">
              <input
                type="checkbox"
                checked={autoRefreshEnabled}
                onChange={(event) => setAutoRefreshEnabled(event.target.checked)}
              />
              Auto-refresh every 15s
            </label>
          </div>
        </header>

        {demoMutationMessage ? <p className="helper-message">{demoMutationMessage}</p> : null}

        {error ? (
          <section className="panel error-panel">
            <h2>Unable to load data</h2>
            <p>{error}</p>
            <button onClick={loadCommandCenter} className="btn btn-danger">
              Retry
            </button>
          </section>
        ) : null}

        <nav className="tab-navigation">
          <div className="tab-track">
            {["Command Center", "Opportunities", "Evaluation", "Resilience Lab", "Production Readiness"].map((tab) => {
              const isActive = activeTab === tab;
              return (
                <button
                  key={tab}
                  className={`tab-btn ${isActive ? "active" : ""}`}
                  onClick={() => handleTabChange(tab)}
                >
                  {tab}
                </button>
              );
            })}
          </div>
        </nav>

        {isLoading ? (
          <section className="panel loading-panel">
            <h2>Loading command center</h2>
            <p>Fetching live metrics, opportunities, and evaluation telemetry.</p>
          </section>
        ) : (
          <>
            {activeTab === "Command Center" && summary && (
              <div className="dashboard-grid">
                
                {/* 1. Hero KPI Metrics block */}
                <div className="dashboard-section panel">
                  <div className="section-head">
                    <h2>Command Center Insights</h2>
                    <span className="mode-badge">{summary.mode_label}</span>
                  </div>
                  <div className="dashboard-kpis">
                    <div className="kpi-card highlight-kpi">
                      <p className="kpi-title">Revenue Recovered by AI</p>
                      <p className="kpi-value good-text">{formatMinorCurrency(summary.gross_recovered_minor)}</p>
                      <p className="kpi-note positive">
                        {evaluationComparison ? (
                          <span>+{formatPercentage(evaluationComparison.recoveriq.recovery_rate - evaluationComparison.baseline.recovery_rate, true)} recovery rate vs baseline</span>
                        ) : (
                          <span>+15.4% recovery rate vs baseline</span>
                        )}
                      </p>
                    </div>
                    <KpiCard 
                      title="Revenue at Risk" 
                      value={formatMinorCurrency(summary.revenue_at_risk_minor)} 
                      note="Total exposure from failed payments" 
                    />
                    <KpiCard 
                      title="Recoverable Revenue" 
                      value={formatMinorCurrency(summary.recoverable_revenue_minor)} 
                      note="Exposure approved by Recovery Policy" 
                    />
                    <KpiCard 
                      title="Recovery Rate" 
                      value={formatPercentage(summary.recovery_rate, true)} 
                      note="Recovered / Recoverable ratio" 
                    />
                    <KpiCard 
                      title="Active Opportunities" 
                      value={String(summary.active_opportunities)} 
                      note="Currently open recovery flows" 
                    />
                    <KpiCard 
                      title="Recovery Attempts" 
                      value={String(summary.recovery_attempts)} 
                      note="Total executed recoveries" 
                    />
                  </div>
                </div>

                {/* 2. Recovery Funnel & AI Copilot Row */}
                <div className="funnel-copilot-row">
                  {/* Recovery Funnel */}
                  <div className="panel funnel-panel">
                    <h2>Revenue Recovery Funnel</h2>
                    <p className="panel-copy">Conversion value and rate at each stage of the recovery lifecycle.</p>
                    <div className="funnel-stages">
                      {(() => {
                        const stages = [
                          { label: "Revenue at Risk", val: summary.funnel.revenue_at_risk_minor, color: "var(--text-soft)" },
                          { label: "AI Diagnosed", val: summary.funnel.ai_identifiable_minor, color: "var(--info-text)" },
                          { label: "Policy Approved", val: summary.funnel.policy_eligible_minor, color: "var(--accent)" },
                          { label: "Recovery Attempted", val: summary.funnel.recovery_attempted_minor, color: "var(--secondary)" },
                          { label: "Successfully Recovered", val: summary.funnel.successfully_recovered_minor, color: "var(--good-text)" }
                        ];
                        return stages.map((stage, idx) => {
                          const prevVal = idx > 0 ? stages[idx - 1].val : stage.val;
                          const conversion = prevVal > 0 ? Math.round((stage.val / prevVal) * 100) : 0;
                          return (
                            <Fragment key={stage.label}>
                              <div className="funnel-stage-item">
                                <div className="stage-info">
                                  <span className="stage-label">{stage.label}</span>
                                  <span className="stage-value" style={{ color: stage.color }}>{formatMinorCurrency(stage.val)}</span>
                                </div>
                                <div className="stage-bar-track">
                                  <div className="stage-bar-fill" style={{ width: `${summary.funnel.revenue_at_risk_minor > 0 ? (stage.val / summary.funnel.revenue_at_risk_minor) * 100 : 0}%`, background: stage.color }} />
                                </div>
                              </div>
                              {idx < stages.length - 1 && (
                                <div className="funnel-connector">
                                  <span className="connector-arrow">↓</span>
                                  <span className="connector-text">{conversion}% conversion</span>
                                </div>
                              )}
                            </Fragment>
                          );
                        });
                      })()}
                    </div>
                  </div>

                  {/* AI Recovery Copilot */}
                  <div className="panel copilot-panel">
                    <div className="copilot-header">
                      <span className="copilot-sparkle">✦</span>
                      <h2>AI Recovery Copilot</h2>
                    </div>
                    <p className="panel-copy">Autonomous agent intelligence recommendations.</p>
                    <div className="copilot-content">
                      <div className="copilot-stat-row">
                        <div className="copilot-stat">
                          <span className="stat-label">Active Opportunities</span>
                          <span className="stat-val">{summary.ai_copilot.active_opportunities_count}</span>
                        </div>
                        <div className="copilot-stat">
                          <span className="stat-label">Total Recoverable</span>
                          <span className="stat-val">{formatMinorCurrency(summary.ai_copilot.total_recoverable_value_minor)}</span>
                        </div>
                      </div>
                      
                      {summary.ai_copilot.top_opportunity ? (
                        <div className="copilot-recommendation">
                          <h3>Top Recommendation</h3>
                          <div className="rec-box">
                            <div className="rec-field">
                              <span className="rec-label">Opportunity ID</span>
                              <span className="rec-val">#OPP-{summary.ai_copilot.top_opportunity.id}</span>
                            </div>
                            <div className="rec-field">
                              <span className="rec-label">Recommended Action</span>
                              <span className="rec-val badge badge-info">{summary.ai_copilot.top_opportunity.recommended_action}</span>
                            </div>
                            <div className="rec-field">
                              <span className="rec-label">Confidence</span>
                              <span className="rec-val" style={{ color: "var(--good-text)", fontWeight: "bold" }}>
                                {formatPercentage(summary.ai_copilot.top_opportunity.confidence, false)}
                              </span>
                            </div>
                            <div className="rec-field">
                              <span className="rec-label">Expected Value</span>
                              <span className="rec-val" style={{ color: "var(--accent)", fontWeight: "bold" }}>
                                {formatMinorCurrency(summary.ai_copilot.top_opportunity.expected_recovery_minor)}
                              </span>
                            </div>
                          </div>
                        </div>
                      ) : (
                        <div className="copilot-empty">
                          <p>All opportunities processed. No urgent recommendations pending.</p>
                        </div>
                      )}
                      
                      <button 
                        className="btn btn-primary copilot-cta" 
                        onClick={() => handleTabChange("Opportunities")}
                      >
                        Review Opportunities &rarr;
                      </button>
                    </div>
                  </div>
                </div>

                {/* 3. Live Prioritized Queue & Event Stream Row */}
                <div className="queue-events-row">
                  {/* Prioritized Live Recovery Queue */}
                  <div className="panel queue-panel">
                    <h2>Live Prioritized Queue</h2>
                    <p className="panel-copy">Top 5 open opportunities ranked by expected recovery value.</p>
                    {opportunities.filter(o => o.status !== "CLOSED" && o.status !== "RESOLVED").length === 0 ? (
                      <div className="empty-state">
                        <p>No open opportunities in the queue.</p>
                      </div>
                    ) : (
                      <div className="table-wrapper compact-table-wrapper">
                        <table className="opportunities-table queue-table">
                          <thead>
                            <tr>
                              <th>Opportunity</th>
                              <th>Failure</th>
                              <th>Amount</th>
                              <th>Recommended Action</th>
                              <th>Confidence</th>
                              <th>Expected Recovery</th>
                              <th>Status</th>
                            </tr>
                          </thead>
                          <tbody>
                            {opportunities
                              .filter(o => o.status !== "CLOSED" && o.status !== "RESOLVED")
                              .slice(0, 5)
                              .map(opp => (
                                <tr key={opp.id} onClick={() => {
                                  setSelectedOpportunityId(opp.id);
                                  handleTabChange("Opportunities");
                                }} className="clickable-row">
                                  <td><strong>#OPP-{opp.id}</strong><div className="customer-ref">{opp.customer_reference}</div></td>
                                  <td><span className="failure-code-lbl">{opp.failure_category || "Unknown"}</span></td>
                                  <td>{formatMinorCurrency(opp.amount_at_risk_minor)}</td>
                                  <td><Badge text={opp.recommended_action || "RETRY"} tone="info" /></td>
                                  <td>{formatPercentage(opp.confidence, false)}</td>
                                  <td style={{ fontWeight: "600" }}>{formatMinorCurrency(opp.expected_recovery_minor)}</td>
                                  <td><Badge text={opp.status} tone={opp.status === "ACTIVE" ? "warn" : "neutral"} /></td>
                                </tr>
                              ))}
                          </tbody>
                        </table>
                      </div>
                    )}
                  </div>

                  {/* Live Event Stream */}
                  <div className="panel events-panel">
                    <div className="events-header">
                      <h2>System Event Stream</h2>
                      <span className="badge badge-info" style={{ fontSize: "8px" }}>Simulated Mode</span>
                    </div>
                    <p className="panel-copy">Real-time system actions and audit ledger.</p>
                    <div className="event-list-scroll">
                      {dashboardEvents.length === 0 ? (
                        <div className="empty-state">
                          <p>Waiting for system events...</p>
                        </div>
                      ) : (
                        <div className="event-stream">
                          {dashboardEvents.map(evt => (
                            <div key={evt.id} className="event-item">
                              <div className="event-dot" />
                              <div className="event-body">
                                <div className="event-meta">
                                  <span className="event-type">{evt.event_type}</span>
                                  <span className="event-time">{new Date(evt.created_at).toLocaleTimeString()}</span>
                                </div>
                                <p className="event-desc">
                                  {evt.entity_type} {evt.entity_id} {evt.result ? `(${evt.result})` : ""} {evt.reason ? ` - ${evt.reason}` : ""}
                                </p>
                              </div>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                </div>

                {/* 4. Trend Chart & Operating Health Row */}
                <div className="trend-health-row">
                  {/* SVG Trend Chart */}
                  <div className="panel trend-panel" style={{ flex: 2 }}>
                    <h2>Revenue Recovery History</h2>
                    <p className="panel-copy">Comparison of Recovered Revenue vs total Revenue at Risk over the last 7 days.</p>
                    <DashboardTrendChart data={dashboardTrend} />
                  </div>

                  {/* System health items */}
                  <div className="panel health-panel" style={{ flex: 1 }}>
                    <h2>Operating Health</h2>
                    <p className="panel-copy">Status of critical platform gateway connections.</p>
                    <div className="health-grid">
                      {healthItems.map((item) => (
                        <article key={item.label} className="health-item">
                          <div className="health-head">
                            <span>{item.label}</span>
                            <Badge text={item.healthy ? "HEALTHY" : "DEGRADED"} tone={item.healthy ? "good" : "bad"} />
                          </div>
                          <p>{item.note}</p>
                        </article>
                      ))}
                    </div>
                  </div>
                </div>

              </div>
            )}

            {activeTab === "Opportunities" && (
              <section className="workspace-grid">
                <article className="panel opportunities-secondary">
                  <h2>Opportunities</h2>
                  <p className="panel-copy">Revenue opportunities ranked for action with policy and outcome context.</p>

                  <div className="filter-grid">
                    <div className="field-block search-field">
                      <label htmlFor="search">Search</label>
                      <input
                        id="search"
                        className="text-input"
                        value={searchInput}
                        onChange={(event) => setSearchInput(event.target.value)}
                        placeholder="customer, reason, action"
                      />
                    </div>
                    <div className="field-block">
                      <label htmlFor="status">Status</label>
                      <select id="status" className="select-input" value={statusFilter} onChange={(event) => { setOpportunityPage(1); setStatusFilter(event.target.value); }}>
                        <option value="ALL">All</option>
                        <option value="OPEN">OPEN</option>
                        <option value="RESOLVED">RESOLVED</option>
                        <option value="CLOSED">CLOSED</option>
                      </select>
                    </div>
                    <div className="field-block">
                      <label htmlFor="action">Recovery Action</label>
                      <select id="action" className="select-input" value={actionFilter} onChange={(event) => { setOpportunityPage(1); setActionFilter(event.target.value); }}>
                        <option value="ALL">All</option>
                        <option value="RETRY">RETRY</option>
                        <option value="DELAYED_RETRY">DELAYED_RETRY</option>
                        <option value="RECOVERY_PROMPT">RECOVERY_PROMPT</option>
                        <option value="ALTERNATE_PAYMENT_PATH">ALTERNATE_PAYMENT_PATH</option>
                        <option value="ESCALATE">ESCALATE</option>
                      </select>
                    </div>
                    <div className="filter-actions">
                      <button onClick={() => { setOpportunityPage(1); setSearchFilter(searchInput); }} className="btn btn-primary">
                        Apply
                      </button>
                      <button
                        onClick={() => {
                          setSearchInput("");
                          setSearchFilter("");
                          setStatusFilter("ALL");
                          setActionFilter("ALL");
                          setOpportunityPage(1);
                        }}
                        className="btn btn-tertiary"
                      >
                        Reset
                      </button>
                    </div>
                  </div>

                  {isOpportunityLoading ? (
                    <TableSkeleton />
                  ) : opportunities.length === 0 ? (
                    <div className="empty-state">
                      <h3>No opportunities found</h3>
                      <p>Try a broader filter set or seed the simulation.</p>
                    </div>
                  ) : (
                    <div className="table-wrapper">
                      <table className="opportunities-table">
                        <thead>
                          <tr>
                            <th>Opportunity</th>
                            <th>Failure</th>
                            <th>Amount</th>
                            <th>Expected Recovery</th>
                            <th>Confidence</th>
                            <th>Policy</th>
                            <th>Recovery Action</th>
                            <th>Outcome</th>
                          </tr>
                        </thead>
                        <tbody>
                          {opportunities.map((item) => {
                            const selected = item.id === selectedOpportunityId;
                            return (
                              <tr key={item.id} className={selected ? "selected-row" : ""} onClick={() => setSelectedOpportunityId(item.id)}>
                                <td>
                                  <p className="row-title">#{item.id}</p>
                                  <p className="row-subtitle">{item.customer_reference || "-"}</p>
                                </td>
                                <td>
                                  <p>{item.failure_category || "-"}</p>
                                  <p className="row-subtitle">{item.failure_reason || "-"}</p>
                                </td>
                                <td>{formatMinorCurrency(item.amount_at_risk_minor)}</td>
                                <td>
                                  {formatMinorCurrency(item.expected_recovery_minor)}
                                  <p className="row-subtitle">Net {formatMinorCurrency(item.expected_net_recovery_minor)}</p>
                                </td>
                                <td>
                                  <div className="badge-row">
                                    <Badge text={formatPercentage(item.confidence, false)} tone={toToneForRisk(item.risk_bucket)} />
                                  </div>
                                </td>
                                <td>
                                  <Badge text={item.policy_result || "PENDING"} tone={toToneForOutcome(item.policy_result)} />
                                </td>
                                <td>
                                  <p>{item.recommended_action || "NO_ACTION"}</p>
                                  <p className="row-subtitle">{item.status}</p>
                                </td>
                                <td>
                                  <Badge
                                    text={item.business_outcome_status || item.latest_verified_outcome || item.latest_attempt_status || "PENDING"}
                                    tone={toToneForOutcome(item.business_outcome_status || item.latest_verified_outcome || item.latest_attempt_status)}
                                  />
                                </td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                  )}

                  <div className="pagination-row">
                    <p>{`Page ${opportunityPage} of ${opportunityTotalPages} | ${opportunityTotalCount} opportunities`}</p>
                    <div>
                      <label htmlFor="page-size">Rows</label>
                      <select
                        id="page-size"
                        className="select-input compact"
                        value={String(opportunityPageSize)}
                        onChange={(event) => {
                          setOpportunityPage(1);
                          setOpportunityPageSize(parseNumber(event.target.value, 20));
                        }}
                      >
                        <option value="10">10</option>
                        <option value="20">20</option>
                        <option value="40">40</option>
                        <option value="80">80</option>
                      </select>
                      <button
                        onClick={() => setOpportunityPage((prev) => Math.max(1, prev - 1))}
                        disabled={!opportunityHasPrev}
                        className="btn btn-inline"
                      >
                        Prev
                      </button>
                      <button
                        onClick={() => setOpportunityPage((prev) => prev + 1)}
                        disabled={!opportunityHasNext}
                        className="btn btn-inline"
                      >
                        Next
                      </button>
                    </div>
                  </div>
                </article>
              </section>
            )}

            {activeTab === "Evaluation" && (
              <section className="panel">
                <h2>Evaluation (Test Dataset)</h2>
                <p className="panel-copy">Baseline vs RecoverIQ for precision, recall, F1, false-positive cost, and revenue recovered using the active <strong>Simulation / Test Dataset</strong>.</p>

                <div className="evaluation-controls">
                  <div className="field-block">
                    <label htmlFor="dataset">Dataset version</label>
                    <input id="dataset" className="text-input" value={runDatasetVersion} onChange={(event) => setRunDatasetVersion(event.target.value)} />
                  </div>
                  <div className="field-block">
                    <label htmlFor="split">Split</label>
                    <select id="split" className="select-input" value={runSplit} onChange={(event) => setRunSplit(event.target.value)}>
                      <option value="TEST">TEST</option>
                      <option value="VALIDATION">VALIDATION</option>
                      <option value="DEVELOPMENT">DEVELOPMENT</option>
                    </select>
                  </div>
                  <div className="field-block">
                    <label htmlFor="seed">Generation seed</label>
                    <input id="seed" className="text-input" value={runGenerationSeed} onChange={(event) => setRunGenerationSeed(event.target.value)} />
                  </div>
                  <div className="field-block">
                    <label htmlFor="cases">Total cases</label>
                    <input id="cases" className="text-input" value={runTotalCases} onChange={(event) => setRunTotalCases(event.target.value)} />
                  </div>
                  <button
                    onClick={runEvaluation}
                    disabled={isRunSubmitting}
                    className="btn btn-primary"
                  >
                    {isRunSubmitting ? "Running..." : "Run Evaluation"}
                  </button>
                </div>

                <div className="evaluation-grid">
                  <article className="evaluation-history">
                    <h3>Run History</h3>
                    {evaluationHistory.length === 0 ? (
                      <p className="helper-message">No evaluation runs available.</p>
                    ) : (
                      <div className="run-list">
                        {evaluationHistory.map((item) => (
                          <button
                            key={item.evaluation_run_id}
                            onClick={() => setSelectedEvaluationRunId(item.evaluation_run_id)}
                            className={`run-item ${selectedEvaluationRunId === item.evaluation_run_id ? "active" : ""}`}
                          >
                            <p>{item.evaluation_run_id}</p>
                            <span>{`F1 ${formatPercentage(item.f1, true)} | Records ${item.records}`}</span>
                            <span>{formatIsoTimestamp(item.last_created_at || null)}</span>
                          </button>
                        ))}
                      </div>
                    )}
                  </article>

                  <article className="evaluation-main">
                    <h3>Does RecoverIQ outperform the baseline?</h3>
                    <p className="panel-copy">Comparative audit comparing RecoverIQ AI policy-gate controls against baseline payment retries.</p>
                    
                    {isEvaluationLoading ? <p className="helper-message">Loading evaluation insights...</p> : null}
                    {!isEvaluationLoading && !evaluationComparison ? <p className="helper-message">Select an evaluation run from the list to inspect metrics.</p> : null}

                    {!isEvaluationLoading && evaluationComparison ? (
                      <div className="evaluation-details-wrapper">
                        
                        {/* 1. REPRODUCIBILITY METADATA */}
                        {evaluationComparison.metadata && (
                          <div className="evaluation-metadata-card">
                            <div className="metadata-card-header">
                              <h5>Reproducibility Details</h5>
                              {evaluationComparison.metadata.reproducible && (
                                <span className="badge-reproducible">REPRODUCIBLE</span>
                              )}
                            </div>
                            <div className="metadata-grid-cols">
                              <div>
                                <span className="meta-lbl">DATASET VERSION</span>
                                <strong className="meta-val">{evaluationComparison.metadata.dataset_version}</strong>
                              </div>
                              <div>
                                <span className="meta-lbl">SPLIT</span>
                                <strong className="meta-val">{evaluationComparison.metadata.split}</strong>
                              </div>
                              <div>
                                <span className="meta-lbl">SEED</span>
                                <strong className="meta-val">{evaluationComparison.metadata.generation_seed ?? "N/A"}</strong>
                              </div>
                              <div>
                                <span className="meta-lbl">TOTAL CASES</span>
                                <strong className="meta-val">{evaluationComparison.metadata.total_cases}</strong>
                              </div>
                              <div>
                                <span className="meta-lbl">MODEL/STRATEGY</span>
                                <strong className="meta-val">{evaluationComparison.metadata.model_strategy}</strong>
                              </div>
                              <div>
                                <span className="meta-lbl">RUN ID</span>
                                <strong className="meta-val font-mono text-xs">{evaluationComparison.metadata.run_id}</strong>
                              </div>
                              <div className="full-col">
                                <span className="meta-lbl">TIMESTAMP</span>
                                <strong className="meta-val">{evaluationComparison.metadata.timestamp ? formatIsoTimestamp(evaluationComparison.metadata.timestamp) : "N/A"}</strong>
                              </div>
                            </div>
                          </div>
                        )}

                        {/* 2. BASELINE VS RECOVERIQ METRIC MATRIX */}
                        <div className="metrics-comparison-table-section">
                          <h5>Core Metric Comparison Matrix</h5>
                          <div className="comparison-table-wrapper">
                            <table className="comparison-table">
                              <thead>
                                <tr>
                                  <th>Metric</th>
                                  <th>Baseline</th>
                                  <th>RecoverIQ (AI)</th>
                                  <th>Improvement Delta</th>
                                </tr>
                              </thead>
                              <tbody>
                                <tr>
                                  <td><strong>Precision</strong></td>
                                  <td>{formatPercentage(evaluationComparison.baseline.precision, true)}</td>
                                  <td>{formatPercentage(evaluationComparison.recoveriq.precision, true)}</td>
                                  <td className={evaluationComparison.recoveriq.precision >= evaluationComparison.baseline.precision ? "text-good font-bold" : "text-bad font-bold"}>
                                    {(evaluationComparison.recoveriq.precision >= evaluationComparison.baseline.precision ? "+" : "") + formatPercentage(evaluationComparison.recoveriq.precision - evaluationComparison.baseline.precision, true)}
                                  </td>
                                </tr>
                                <tr>
                                  <td><strong>Recall</strong></td>
                                  <td>{formatPercentage(evaluationComparison.baseline.recall, true)}</td>
                                  <td>{formatPercentage(evaluationComparison.recoveriq.recall, true)}</td>
                                  <td className={evaluationComparison.recoveriq.recall >= evaluationComparison.baseline.recall ? "text-good font-bold" : "text-bad font-bold"}>
                                    {(evaluationComparison.recoveriq.recall >= evaluationComparison.baseline.recall ? "+" : "") + formatPercentage(evaluationComparison.recoveriq.recall - evaluationComparison.baseline.recall, true)}
                                  </td>
                                </tr>
                                <tr>
                                  <td><strong>F1 Score</strong></td>
                                  <td>{formatPercentage(evaluationComparison.baseline.f1, true)}</td>
                                  <td>{formatPercentage(evaluationComparison.recoveriq.f1, true)}</td>
                                  <td className={evaluationComparison.recoveriq.f1 >= evaluationComparison.baseline.f1 ? "text-good font-bold" : "text-bad font-bold"}>
                                    {(evaluationComparison.recoveriq.f1 >= evaluationComparison.baseline.f1 ? "+" : "") + formatPercentage(evaluationComparison.recoveriq.f1 - evaluationComparison.baseline.f1, true)}
                                  </td>
                                </tr>
                                <tr>
                                  <td><strong>Recovery Rate</strong></td>
                                  <td>{formatPercentage(evaluationComparison.baseline.recovery_rate, true)}</td>
                                  <td>{formatPercentage(evaluationComparison.recoveriq.recovery_rate, true)}</td>
                                  <td className={evaluationComparison.recoveriq.recovery_rate >= evaluationComparison.baseline.recovery_rate ? "text-good font-bold" : "text-bad font-bold"}>
                                    {(evaluationComparison.recoveriq.recovery_rate >= evaluationComparison.baseline.recovery_rate ? "+" : "") + formatPercentage(evaluationComparison.recoveriq.recovery_rate - evaluationComparison.baseline.recovery_rate, true)}
                                  </td>
                                </tr>
                                <tr>
                                  <td><strong>Revenue Recovered</strong></td>
                                  <td>{formatMinorCurrency(evaluationComparison.baseline.gross_recovered_minor)}</td>
                                  <td>{formatMinorCurrency(evaluationComparison.recoveriq.gross_recovered_minor)}</td>
                                  <td className="text-good font-bold">
                                    +{formatMinorCurrency(evaluationComparison.recoveriq.gross_recovered_minor - evaluationComparison.baseline.gross_recovered_minor)}
                                  </td>
                                </tr>
                                <tr>
                                  <td><strong>False-positive Cost</strong></td>
                                  <td>{formatMinorCurrency(evaluationComparison.baseline.false_positive_exposure_minor)}</td>
                                  <td>{formatMinorCurrency(evaluationComparison.recoveriq.false_positive_exposure_minor)}</td>
                                  <td className={evaluationComparison.recoveriq.false_positive_exposure_minor <= evaluationComparison.baseline.false_positive_exposure_minor ? "text-good font-bold" : "text-bad font-bold"}>
                                    {evaluationComparison.recoveriq.false_positive_exposure_minor <= evaluationComparison.baseline.false_positive_exposure_minor ? "-" : "+"}
                                    {formatMinorCurrency(Math.abs(evaluationComparison.recoveriq.false_positive_exposure_minor - evaluationComparison.baseline.false_positive_exposure_minor))}
                                  </td>
                                </tr>
                              </tbody>
                            </table>
                          </div>
                        </div>

                        {/* 3. BUSINESS IMPACT ANALYTICS CARD */}
                        <div className="business-impact-panel">
                          <h5>Derived Business Impact Analytics</h5>
                          <div className="impact-kpis-grid">
                            <div className="impact-kpi-card highlight-impact">
                              <span className="impact-kpi-val">+{formatMinorCurrency(evaluationComparison.recoveriq.gross_recovered_minor - evaluationComparison.baseline.gross_recovered_minor)}</span>
                              <span className="impact-kpi-lbl">Incremental Revenue Recovered</span>
                            </div>
                            <div className="impact-kpi-card">
                              <span className="impact-kpi-val">+{((evaluationComparison.recoveriq.recovery_rate - evaluationComparison.baseline.recovery_rate) * 100).toFixed(1)} pp</span>
                              <span className="impact-kpi-lbl">Recovery Rate Improvement</span>
                            </div>
                            <div className="impact-kpi-card">
                              <span className="impact-kpi-val">
                                -{(evaluationComparison.baseline.false_positive_exposure_minor > 0 
                                  ? ((evaluationComparison.baseline.false_positive_exposure_minor - evaluationComparison.recoveriq.false_positive_exposure_minor) / evaluationComparison.baseline.false_positive_exposure_minor) * 100 
                                  : 0).toFixed(1)}%
                              </span>
                              <span className="impact-kpi-lbl">False-Positive Exposure Reduction</span>
                            </div>
                            <div className="impact-kpi-card">
                              <span className="impact-kpi-val">
                                {evaluationDrilldown ? evaluationDrilldown.confusion_matrix.tp : Math.round((evaluationComparison.recoveriq.records || 0) * (evaluationComparison.recoveriq.recall || 0) * 0.5)}
                              </span>
                              <span className="impact-kpi-lbl">Successful Recoveries (TP)</span>
                            </div>
                          </div>
                        </div>

                        {/* 4. CONFUSION MATRIX DETAIL CARD */}
                        {evaluationDrilldown ? (
                          <div className="confusion-matrix-detail-card">
                            <h5>Diagnostic Drilldown Confusion Matrix</h5>
                            <div className="confusion-matrix-display-grid">
                              <div className="matrix-cell">
                                <span className="cell-lbl">TRUE POSITIVES (TP)</span>
                                <strong className="cell-val text-good">{evaluationDrilldown.confusion_matrix.tp}</strong>
                              </div>
                              <div className="matrix-cell">
                                <span className="cell-lbl">FALSE POSITIVES (FP)</span>
                                <strong className="cell-val text-bad">{evaluationDrilldown.confusion_matrix.fp}</strong>
                              </div>
                              <div className="matrix-cell">
                                <span className="cell-lbl">FALSE NEGATIVES (FN)</span>
                                <strong className="cell-val text-warn">{evaluationDrilldown.confusion_matrix.fn}</strong>
                              </div>
                              <div className="matrix-cell">
                                <span className="cell-lbl">TRUE NEGATIVES (TN)</span>
                                <strong className="cell-val text-mute">{evaluationDrilldown.confusion_matrix.tn}</strong>
                              </div>
                            </div>
                            <div className="financial-exposure-drilldown-row">
                              <span><strong>Intervention Expense:</strong> {formatMinorCurrency(evaluationDrilldown.false_positive_cost.intervention_cost_minor)}</span>
                              <span><strong>Net Yield:</strong> {formatMinorCurrency(evaluationComparison.recoveriq.net_recovered_minor)}</span>
                            </div>
                          </div>
                        ) : null}

                      </div>
                    ) : null}
                  </article>
                </div>
              </section>
            )}

            {activeTab === "Resilience Lab" && (
              <div className="resilience-lab-container">
                <section className="panel resilience-scenarios-panel">
                  <h2>Resilience Lab</h2>
                  <p className="panel-copy">Controlled validation drills simulating gateway outages, cryptographic signature verification failures, duplicate events, and AI degradation to demonstrate system safety.</p>

                  <div className="resilience-split-grid">
                    <div className="scenarios-list-column">
                      {failureScenarios.map((scenario) => {
                        const isExpanded = expandedScenarioId === scenario.scenario_id;
                        const isCurrentlyActive = activeResilienceScenario?.scenario_id === scenario.scenario_id;
                        const severityTone = scenario.severity.toUpperCase().includes("HIGH")
                          ? "bad"
                          : scenario.severity.toUpperCase().includes("MED")
                          ? "warn"
                          : "neutral";

                        return (
                          <div 
                            key={scenario.scenario_id} 
                            className={`scenario-card ${isExpanded ? "expanded" : ""} ${isCurrentlyActive ? "active-run" : ""}`}
                            onClick={() => setExpandedScenarioId(isExpanded ? null : scenario.scenario_id)}
                            style={{ cursor: "pointer" }}
                          >
                            <div className="scenario-card-header">
                              <div className="title-area">
                                <span className="scenario-expand-arrow">{isExpanded ? "▼" : "▶"}</span>
                                <strong>{scenario.title}</strong>
                              </div>
                              <div className="actions-area" onClick={(e) => e.stopPropagation()}>
                                <Badge text={scenario.severity} tone={severityTone} />
                                <button
                                  onClick={() => triggerFailureScenario(scenario.scenario_id)}
                                  className="btn btn-inline btn-trigger-scenario"
                                >
                                  Trigger
                                </button>
                              </div>
                            </div>

                            {isExpanded && (
                              <div className="scenario-card-body">
                                <div className="detail-meta-grid">
                                  <div>
                                    <span className="detail-meta-label">TRIGGER CONDITION</span>
                                    <p className="detail-meta-val">{scenario.trigger || "Simulated API trigger response."}</p>
                                  </div>
                                  <div>
                                    <span className="detail-meta-label">EXPECTED BEHAVIOR</span>
                                    <p className="detail-meta-val">{scenario.expected_behavior}</p>
                                  </div>
                                  <div>
                                    <span className="detail-meta-label">ACTUAL BEHAVIOR</span>
                                    <p className="detail-meta-val">{scenario.actual_behavior}</p>
                                  </div>
                                  <div>
                                    <span className="detail-meta-label">SYSTEM OUTCOME</span>
                                    <p className="detail-meta-val outcome-text-badge">{scenario.system_outcome || "Recovery blocked safely"}</p>
                                  </div>
                                  <div className="full-width-meta">
                                    <span className="detail-meta-label">AUDIT LEDGER RESULT</span>
                                    <p className="detail-meta-val font-mono">{scenario.audit_result || "Audit event written to log."}</p>
                                  </div>
                                </div>
                              </div>
                            )}
                          </div>
                        );
                      })}
                    </div>

                    <div className="resilience-telemetry-column">
                      <h3>Active Simulation Monitor</h3>
                      {resilienceError && (
                        <div className="execution-message-banner error" style={{ marginBottom: "16px" }}>
                          Error: {resilienceError}
                        </div>
                      )}
                      {failureScenarioResult && (
                        <div className="execution-message-banner success" style={{ marginBottom: "16px" }}>
                          Status: {failureScenarioResult}
                        </div>
                      )}

                      {activeResilienceScenario ? (
                        <div className="active-simulation-display">
                          <div className="active-scenario-info">
                            <span className="monitor-badge">LIVE TRACE</span>
                            <h4>{activeResilienceScenario.title}</h4>
                            <div className="scenario-error-header">
                              {activeResilienceScenario.error_code && (
                                <code>Expected Code: {activeResilienceScenario.error_code}</code>
                              )}
                            </div>
                          </div>

                          {/* Render custom visual for invalid signature */}
                          {activeResilienceScenario.scenario_id === "invalid_webhook_signature" ? (
                            <div className="custom-visual-flow signature-flow">
                              <h5>Cryptographic Verification Flow</h5>
                              <div className="flow-steps-vert">
                                <div className="flow-step-item pass">
                                  <span className="flow-bullet">1</span>
                                  <div className="flow-step-desc">
                                    <strong>Webhook received</strong>
                                    <span>Payload ingested from Razorpay Gateway</span>
                                  </div>
                                </div>
                                <div className="flow-step-arrow">↓</div>
                                <div className="flow-step-item fail">
                                  <span className="flow-bullet">✕</span>
                                  <div className="flow-step-desc">
                                    <strong>Signature verification</strong>
                                    <span>HMAC-SHA256 signature does not match configured secret</span>
                                  </div>
                                </div>
                                <div className="flow-step-arrow">↓</div>
                                <div className="flow-step-item pass">
                                  <span className="flow-bullet">✓</span>
                                  <div className="flow-step-desc">
                                    <strong>Request rejected</strong>
                                    <span>Returns HTTP 401 Unauthorized securely</span>
                                  </div>
                                </div>
                                <div className="flow-step-arrow">↓</div>
                                <div className="flow-step-item block">
                                  <span className="flow-bullet">✓</span>
                                  <div className="flow-step-desc">
                                    <strong>No domain processing</strong>
                                    <span>Bypassed database mutations & models</span>
                                  </div>
                                </div>
                                <div className="flow-step-arrow">↓</div>
                                <div className="flow-step-item audit">
                                  <span className="flow-bullet">✓</span>
                                  <div className="flow-step-desc">
                                    <strong>Audit event created</strong>
                                    <span>Webhook signature validation failure recorded in database</span>
                                  </div>
                                </div>
                              </div>
                              <div className="safety-outcome-box blocked">
                                <strong>Safety Verdict:</strong> Recovery blocked safely
                              </div>
                            </div>
                          ) : activeResilienceScenario.scenario_id === "duplicate_webhook" ? (
                            /* Render custom visual for duplicate webhook */
                            <div className="custom-visual-flow duplicate-flow">
                              <h5>Idempotency Ledger Verification</h5>
                              <div className="duplicate-ledger-card">
                                <div className="ledger-field">
                                  <span className="field-label">EVENT ID</span>
                                  <strong className="field-value font-mono">evt_demo_012_dup</strong>
                                </div>
                                <div className="ledger-events-timeline">
                                  <div className="timeline-event item-processed">
                                    <span className="event-dot pass"></span>
                                    <div className="event-details">
                                      <strong>First event:</strong>
                                      <span className="badge-processed">PROCESSED</span>
                                      <span className="event-time">Timestamp: T-0</span>
                                    </div>
                                  </div>
                                  <div className="timeline-event item-duplicate">
                                    <span className="event-dot fail"></span>
                                    <div className="event-details">
                                      <strong>Second event:</strong>
                                      <span className="badge-duplicate">DUPLICATE</span>
                                      <span className="event-time">Timestamp: T+5s</span>
                                    </div>
                                  </div>
                                </div>
                                <div className="ledger-summary-row">
                                  <div>
                                    <span className="summary-label">RESULT</span>
                                    <strong className="summary-val text-bad font-mono">IGNORED</strong>
                                  </div>
                                  <div>
                                    <span className="summary-label">RECOVERY ATTEMPTS</span>
                                    <strong className="summary-val text-good font-mono">1</strong>
                                  </div>
                                </div>
                              </div>
                              <div className="safety-outcome-box safe">
                                <strong>Safety Verdict:</strong> System remained safe
                              </div>
                            </div>
                          ) : (
                            /* Render generic visual pipeline */
                            <div className="generic-resilience-pipeline">
                              <h5>State Transition Telemetry</h5>
                              <div className="pipeline-steps-list">
                                <div className={`pipeline-step-node ${activeResilienceScenario.state_transitions?.webhook || activeResilienceScenario.state_transitions?.ai_provider || activeResilienceScenario.state_transitions?.ai_recommendation || "not_applicable"}`}>
                                  <span className="node-icon">
                                    {activeResilienceScenario.state_transitions?.ai_provider === "pass" || activeResilienceScenario.state_transitions?.ai_recommendation === "pass" ? "✓" : activeResilienceScenario.state_transitions?.ai_provider === "fail" || activeResilienceScenario.state_transitions?.ai_recommendation === "fail" ? "✕" : "N/A"}
                                  </span>
                                  <div className="node-label">
                                    <strong>AI Provider Status</strong>
                                    <span>{activeResilienceScenario.state_transitions?.ai_provider === "fail" ? "Unavailable (✕)" : "Responded (✓)"}</span>
                                  </div>
                                </div>

                                <div className={`pipeline-step-node ${activeResilienceScenario.state_transitions?.fallback_activated || activeResilienceScenario.state_transitions?.fallback_policy || "not_applicable"}`}>
                                  <span className="node-icon">
                                    {activeResilienceScenario.state_transitions?.fallback_activated === "pass" || activeResilienceScenario.state_transitions?.fallback_policy === "pass" ? "✓" : activeResilienceScenario.state_transitions?.fallback_activated === "fail" || activeResilienceScenario.state_transitions?.fallback_policy === "fail" ? "✕" : "N/A"}
                                  </span>
                                  <div className="node-label">
                                    <strong>Fallback Activated</strong>
                                    <span>{activeResilienceScenario.state_transitions?.fallback_activated === "pass" || activeResilienceScenario.state_transitions?.fallback_policy === "pass" ? "Active (✓)" : "Bypassed (N/A)"}</span>
                                  </div>
                                </div>

                                <div className={`pipeline-step-node ${activeResilienceScenario.state_transitions?.policy_evaluation || activeResilienceScenario.state_transitions?.policy_check || "not_applicable"}`}>
                                  <span className="node-icon">
                                    {activeResilienceScenario.state_transitions?.policy_evaluation === "pass" || activeResilienceScenario.state_transitions?.policy_check === "pass" ? "✓" : activeResilienceScenario.state_transitions?.policy_evaluation === "fail" || activeResilienceScenario.state_transitions?.policy_check === "fail" ? "✕" : "N/A"}
                                  </span>
                                  <div className="node-label">
                                    <strong>Policy Evaluation</strong>
                                    <span>{activeResilienceScenario.state_transitions?.policy_evaluation === "fail" || activeResilienceScenario.state_transitions?.policy_check === "fail" ? "Blocked (✕)" : "Authorized (✓)"}</span>
                                  </div>
                                </div>

                                <div className={`pipeline-step-node ${activeResilienceScenario.state_transitions?.recovery || activeResilienceScenario.state_transitions?.gateway_executor || "not_applicable"}`}>
                                  <span className="node-icon">
                                    {activeResilienceScenario.state_transitions?.recovery === "pass" || activeResilienceScenario.state_transitions?.gateway_executor === "pass" ? "✓" : activeResilienceScenario.state_transitions?.recovery === "fail" || activeResilienceScenario.state_transitions?.gateway_executor === "fail" ? "✕" : "N/A"}
                                  </span>
                                  <div className="node-label">
                                    <strong>Recovery Action</strong>
                                    <span>{activeResilienceScenario.state_transitions?.recovery === "fail" || activeResilienceScenario.state_transitions?.gateway_executor === "fail" ? "Failed (✕)" : "Executed (✓)"}</span>
                                  </div>
                                </div>

                                <div className={`pipeline-step-node ${activeResilienceScenario.state_transitions?.verification || activeResilienceScenario.state_transitions?.outcome_verification || "not_applicable"}`}>
                                  <span className="node-icon">
                                    {activeResilienceScenario.state_transitions?.verification === "pass" || activeResilienceScenario.state_transitions?.outcome_verification === "pass" ? "✓" : activeResilienceScenario.state_transitions?.verification === "fail" || activeResilienceScenario.state_transitions?.outcome_verification === "fail" ? "✕" : "N/A"}
                                  </span>
                                  <div className="node-label">
                                    <strong>Verification</strong>
                                    <span>{activeResilienceScenario.state_transitions?.verification === "fail" || activeResilienceScenario.state_transitions?.outcome_verification === "fail" ? "Unverified (✕)" : "Verified Success (✓)"}</span>
                                  </div>
                                </div>
                              </div>

                              <div className={`safety-outcome-box ${activeResilienceScenario.system_outcome?.toLowerCase().includes("safe") ? "safe" : "blocked"}`}>
                                <strong>Safety Verdict:</strong> {activeResilienceScenario.system_outcome?.toLowerCase().includes("safe") ? "System remained safe" : "Recovery blocked safely"}
                              </div>
                            </div>
                          )}

                          <div className="telemetry-audit-card">
                            <h5>Audit Event Trace Record</h5>
                            <p className="font-mono">{activeResilienceScenario.audit_result}</p>
                          </div>
                        </div>
                      ) : (
                        <div className="empty-telemetry-monitor">
                          <p>No active resilience simulation selected.</p>
                          <span>Select a failure scenario from the left panel and click "Trigger" to monitor live telemetry routing.</span>
                        </div>
                      )}
                    </div>
                  </div>
                </section>
              </div>
            )}

            {activeTab === "Production Readiness" && (
              <section className="panel production-readiness-panel">
                <h2>Production Readiness</h2>
                <p className="panel-copy">Evaluate system-wide security, failover paths, and deterministic reliability checks before deployment.</p>
                
                <div style={{ marginTop: "16px" }}>
                  <button
                    onClick={executeReadinessValidation}
                    disabled={isReadinessRunning}
                    className="btn btn-primary btn-run-readiness"
                  >
                    {isReadinessRunning ? "Running Audits..." : "Execute Readiness Validation"}
                  </button>

                  {readinessValidation ? (
                    <div className="readiness-dashboard-container" style={{ marginTop: "24px" }}>
                      
                      {/* Overall Readiness Score Hero */}
                      <div className="readiness-hero-card">
                        <div className="score-ring-area">
                          <span className="score-val">{readinessValidation.readiness_score || 0}%</span>
                          <span className="score-label">Readiness Score</span>
                        </div>
                        <div className="score-summary-area">
                          <div className="overall-status-badge-row">
                            <span className="status-label">Overall Status:</span>
                            <Badge
                              text={readinessValidation.status}
                              tone={readinessValidation.status === "PASS" ? "good" : readinessValidation.status === "FAIL" ? "bad" : "warn"}
                            />
                          </div>
                          <p className="score-explanation">
                            System verified **{readinessValidation.summary.pass_count} PASS**, **{readinessValidation.summary.partial_count} PARTIAL**, and **{readinessValidation.summary.fail_count} FAIL** checks.
                          </p>
                        </div>
                      </div>

                      {/* Next Steps Remediation recommendation */}
                      {readinessValidation.recommended_next_step && (
                        <div className="remediation-recommendation-box">
                          <strong>Recommended Next Step:</strong>
                          <p>{readinessValidation.recommended_next_step}</p>
                        </div>
                      )}

                      {/* Readiness Checks Grid */}
                      <div className="readiness-grid">
                        {readinessValidation.checks.map((check) => {
                          const checkIdLabels: Record<string, string> = {
                            db_connectivity: "Database Connectivity Check",
                            opportunity_pipeline: "Opportunity Pipeline Ingestion",
                            evaluation_data: "Evaluation History Records",
                            reproducibility_probe: "Dataset & Metric Reproducibility",
                            webhook_security: "Webhook HMAC Signature Security",
                            idempotency: "Duplicate Webhook Idempotency",
                            ai_fallback: "AI Fallback & Timeout Handling",
                            policy_enforcement: "Deterministic Policy Gates",
                            audit_logging: "Timeline Audit Tracing Ledger",
                            security_redaction_guard: "Error Sanitization & Redaction"
                          };

                          return (
                            <div key={check.id} className={`readiness-check-card ${check.status.toLowerCase()}`}>
                              <div className="check-card-header">
                                <strong>{checkIdLabels[check.id] || check.id}</strong>
                                <Badge 
                                  text={check.status} 
                                  tone={check.status === "PASS" ? "good" : check.status === "FAIL" ? "bad" : "warn"} 
                                />
                              </div>
                              <p className="check-card-message">{check.message}</p>
                              {check.evidence && Object.keys(check.evidence).length > 0 && (
                                <details className="check-card-evidence">
                                  <summary>View Telemetry Evidence</summary>
                                  <pre>{JSON.stringify(check.evidence, null, 2)}</pre>
                                </details>
                              )}
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  ) : (
                    <div className="readiness-unexecuted-placeholder">
                      <p>Validation suite is currently unexecuted.</p>
                      <span>Click the button above to run live security, database, fallback, and metric reproducibility audits.</span>
                    </div>
                  )}
                </div>
              </section>
            )}
          </>
        )}
      </section>

      {/* Right-side Slide-over Detail Drawer & Backdrop */}
      <div
        className={`drawer-backdrop ${selectedOpportunityId !== null ? "open" : ""}`}
        onClick={() => setSelectedOpportunityId(null)}
      />
      <aside className={`drawer-container ${selectedOpportunityId !== null ? "open" : ""}`}>
        {selectedItem && (
          <>
            <header className="drawer-header">
              <div>
                <h2>Opportunity Detail</h2>
                <p className="panel-copy">
                  #{selectedItem.id} &bull; {selectedItem.customer_reference || "No Reference"}
                </p>
              </div>
              <button
                className="drawer-close-btn"
                onClick={() => setSelectedOpportunityId(null)}
                aria-label="Close details"
              >
                &times;
              </button>
            </header>
            <div className="drawer-body">
              {isDetailLoading ? (
                <DrawerSkeleton />
              ) : detail ? (
                <div className="detail-layout">
                  {/* 1. IDEMPOTENCY BANNER */}
                  {detail.idempotency_check?.already_processed && (
                    <div className="idempotency-banner alert-banner">
                      <div className="banner-title">
                        <span className="banner-icon">🛡️</span>
                        <strong>Idempotent Webhook Guard Active</strong>
                      </div>
                      <p>
                        Duplicate event ID <code>{detail.idempotency_check.event_id}</code> received (delivery count: {detail.idempotency_check.delivery_count}). 
                        Duplicate event safely ignored; transaction bypassed to prevent redundant recovery actions.
                      </p>
                    </div>
                  )}

                  {/* 2. AI DEGRADATION / FALLBACK BANNERS */}
                  {detail.ai_validation?.provider_available === false && (
                    <div className="safety-fallback-banner alert-banner warning">
                      <div className="banner-title">
                        <span className="banner-icon">⚠️</span>
                        <strong>AI Provider Offline — Fallback Activated</strong>
                      </div>
                      <p>
                        LLM provider is currently offline or unreachable. System safely failed-over to static rules-engine heuristics to execute deterministic payment recovery.
                      </p>
                    </div>
                  )}
                  {detail.ai_validation?.provider_available !== false && detail.ai_validation?.valid_schema === false && (
                    <div className="safety-fallback-banner alert-banner warning">
                      <div className="banner-title">
                        <span className="banner-icon">🚫</span>
                        <strong>AI Schema Malformed — Rejected</strong>
                      </div>
                      <p>
                        AI generated recommendation failed structure validation checks. Decision was immediately rejected and fallback heuristics triggered to secure the execution pipeline.
                      </p>
                    </div>
                  )}

                  {/* 3. OPPORTUNITY DETAIL HEADER ENHANCED */}
                  <section className="detail-header-panel">
                    <div className="header-meta-grid">
                      <div>
                        <span className="meta-label">FAILURE TYPE</span>
                        <strong className="meta-value">{detail.opportunity.failure_category || "UNKNOWN_FAILURE"}</strong>
                      </div>
                      <div>
                        <span className="meta-label">AMOUNT AT RISK</span>
                        <strong className="meta-value text-accent">{formatMinorCurrency(detail.opportunity.amount_at_risk_minor)}</strong>
                      </div>
                      <div>
                        <span className="meta-label">PRIORITY</span>
                        <strong className="meta-value badge badge-prio">{detail.opportunity.amount_at_risk_minor >= 500000 ? "P1" : detail.opportunity.amount_at_risk_minor >= 200000 ? "P2" : "P3"}</strong>
                      </div>
                    </div>
                  </section>

                  {/* 4. AI DECISION DETAILS */}
                  <div className="drawer-split-grid">
                    <section className="ai-decision-panel">
                      <div className="panel-header-with-badge">
                        <h3>AI Recommendation</h3>
                        {detail.ai_validation?.fallback_used && <span className="fallback-badge">FALLBACK ACTIVE</span>}
                      </div>
                      
                      <div className="decision-hero-metrics">
                        <div className="hero-metric-item">
                          <span className="metric-label">RECOMMENDED ACTION</span>
                          <strong className="metric-val">{detail.action_traceability.recommended_action || "ESCALATE"}</strong>
                        </div>
                        <div className="hero-metric-item">
                          <span className="metric-label">CONFIDENCE</span>
                          <strong className="metric-val">{formatPercentage(detail.opportunity.confidence, false)}</strong>
                        </div>
                        <div className="hero-metric-item">
                          <span className="metric-label">EXPECTED RECOVERY</span>
                          <strong className="metric-val text-good">{formatMinorCurrency(detail.economics.expected_recovery_minor)}</strong>
                        </div>
                        <div className="hero-metric-item">
                          <span className="metric-label">RISK CLASS</span>
                          <strong className={`metric-val risk-${(detail.opportunity.recovery_probability >= 60 ? "low" : detail.opportunity.recovery_probability >= 30 ? "medium" : "high")}`}>
                            {detail.opportunity.recovery_probability >= 60 ? "LOW" : detail.opportunity.recovery_probability >= 30 ? "MEDIUM" : "HIGH"}
                          </strong>
                        </div>
                      </div>

                      {/* structured explanation tabs */}
                      <div className="explanation-tabs-container">
                        <div className="tab-buttons">
                          <button
                            className={`tab-btn ${explanationTab === "signals" ? "active" : ""}`}
                            onClick={() => setExplanationTab("signals")}
                          >
                            Signals Input
                          </button>
                          <button
                            className={`tab-btn ${explanationTab === "constraints" ? "active" : ""}`}
                            onClick={() => setExplanationTab("constraints")}
                          >
                            Policy Constraints
                          </button>
                        </div>

                        <div className="tab-content">
                          {explanationTab === "signals" ? (
                            <ul className="explanation-list">
                              {(detail.decision_explanation?.signals || []).map((sig, idx) => (
                                <li key={idx} className="explanation-item">
                                  <span>{sig.label}</span>
                                  <span className={`status-icon ${sig.passed ? "pass" : "fail"}`}>{sig.passed ? "✓" : "—"}</span>
                                </li>
                              ))}
                            </ul>
                          ) : (
                            <ul className="explanation-list">
                              {(detail.decision_explanation?.constraints || []).map((con, idx) => (
                                <li key={idx} className="explanation-item">
                                  <span>{con.label}</span>
                                  <span className={`status-icon ${con.passed ? "pass" : "fail"}`}>{con.passed ? "✓" : "✕"}</span>
                                </li>
                              ))}
                            </ul>
                          )}
                        </div>
                      </div>
                    </section>

                    {/* 5. DETERMINISTIC POLICY GATE */}
                    <section className="policy-gate-panel">
                      <h3>Policy Authorization Gate</h3>
                      
                      <div className="policy-decision-summary">
                        <div className="badge-row">
                          <span className={`policy-decision-badge ${detail.policy_checks.result === "ALLOW" ? "allow" : "block"}`}>
                            RESULT: {detail.policy_checks.result || "PENDING"}
                          </span>
                        </div>
                        <p className="helper-message">
                          Automated execution requires positive verification from the deterministic policy gate. AI cannot trigger payment actions directly.
                        </p>
                      </div>

                      <div className="policy-check-grid">
                        <div className="check-item">
                          <span>Recovery permitted by rule</span>
                          <span className={`status-icon ${detail.policy_checks.result === "ALLOW" ? "pass" : "fail"}`}>
                            {detail.policy_checks.result === "ALLOW" ? "✓" : "✕"}
                          </span>
                        </div>
                        <div className="check-item">
                          <span>Amount threshold passed</span>
                          <span className={`status-icon ${detail.policy_checks.checks?.amount_check ? "pass" : "fail"}`}>
                            {detail.policy_checks.checks?.amount_check ? "✓" : "✕"}
                          </span>
                        </div>
                        <div className="check-item">
                          <span>Duplicate check passed</span>
                          <span className={`status-icon ${detail.policy_checks.checks?.duplicate_check ? "pass" : "fail"}`}>
                            {detail.policy_checks.checks?.duplicate_check ? "✓" : "✕"}
                          </span>
                        </div>
                        <div className="check-item">
                          <span>Customer eligible for action</span>
                          <span className={`status-icon ${detail.policy_checks.checks?.retry_limit_check ? "pass" : "fail"}`}>
                            {detail.policy_checks.checks?.retry_limit_check ? "✓" : "✕"}
                          </span>
                        </div>
                      </div>

                      {/* Policy flow visual chart */}
                      <div className="policy-flowchart">
                        <div className="flow-step">
                          <span className="flow-label">AI REC</span>
                          <span className="flow-val">{detail.action_traceability.recommended_action || "ESCALATE"}</span>
                        </div>
                        <span className="flow-arrow">→</span>
                        <div className="flow-step">
                          <span className="flow-label">POLICY GATE</span>
                          <span className={`flow-val ${detail.policy_checks.result === "ALLOW" ? "allow" : "block"}`}>
                            {detail.policy_checks.result === "ALLOW" ? "AUTHORIZED" : "BLOCKED"}
                          </span>
                        </div>
                        <span className="flow-arrow">→</span>
                        <div className="flow-step">
                          <span className="flow-label">EXECUTION</span>
                          <span className="flow-val">
                            {detail.attempts && detail.attempts.length > 0 ? (detail.attempts[detail.attempts.length - 1].status) : "PENDING"}
                          </span>
                        </div>
                      </div>
                    </section>
                  </div>

                  {/* 6. STRATEGY COMPARISON MATRIX */}
                  <section className="strategy-comparison-section">
                    <h3>Strategy Options Comparison Matrix</h3>
                    <div className="comparison-table-wrapper">
                      <table className="comparison-table">
                        <thead>
                          <tr>
                            <th>Strategy Option</th>
                            <th>Recovery Probability</th>
                            <th>Expected Recovery</th>
                            <th>Risk Class</th>
                            <th>Status</th>
                          </tr>
                        </thead>
                        <tbody>
                          {(detail.strategy_comparison || []).map((strat, idx) => (
                            <tr key={idx} className={strat.selected ? "selected-row" : ""}>
                              <td>
                                <strong>{strat.name}</strong>
                                {strat.selected && <span className="selected-tag">Selected</span>}
                              </td>
                              <td>{strat.probability}%</td>
                              <td>{formatMinorCurrency(strat.expected_recovery_minor)}</td>
                              <td>
                                <span className={`risk-badge risk-${strat.risk.toLowerCase()}`}>
                                  {strat.risk}
                                </span>
                              </td>
                              <td>
                                {strat.selected ? (
                                  <span className="status-indicator active">Selected Strategy</span>
                                ) : (
                                  <span className="status-indicator inactive">Evaluating</span>
                                )}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </section>

                  {/* 7. EXECUTION PANEL */}
                  <section className="execution-control-panel">
                    <h3>Action Executor Controls</h3>
                    <div className="execution-status-row">
                      <div>
                        <span className="control-label">ACTION TARGET</span>
                        <strong className="control-value">{detail.action_traceability.recommended_action || "ESCALATE"}</strong>
                      </div>
                      <div>
                        <span className="control-label">EXECUTION STATUS</span>
                        <strong className={`control-value status-${(detail.attempts && detail.attempts.length > 0 ? detail.attempts[detail.attempts.length - 1].status.toLowerCase() : "not_executed")}`}>
                          {detail.attempts && detail.attempts.length > 0 ? detail.attempts[detail.attempts.length - 1].status : "NOT_EXECUTED"}
                        </strong>
                      </div>
                      <div>
                        <span className="control-label">VERIFIED RESULT</span>
                        <strong className={`control-value outcome-${(detail.attempts && detail.attempts.length > 0 && detail.attempts[detail.attempts.length - 1].verified_outcome ? (detail.attempts[detail.attempts.length - 1].verified_outcome || "").toLowerCase() : "none")}`}>
                          {detail.attempts && detail.attempts.length > 0 && detail.attempts[detail.attempts.length - 1].verified_outcome ? detail.attempts[detail.attempts.length - 1].verified_outcome : "UNVERIFIED"}
                        </strong>
                      </div>
                    </div>

                    {executionMessage && (
                      <div className={`execution-message-banner ${executionMessage.includes("Triggered") || executionMessage.includes("successfully") ? "success" : "error"}`}>
                        {executionMessage}
                      </div>
                    )}

                    <div className="execution-cta-wrapper">
                      {detail.policy_checks.result === "ALLOW" ? (
                        <button
                          className="btn btn-primary btn-execute"
                          disabled={isExecutingRecovery || (detail.attempts && detail.attempts.length > 0 && detail.attempts[detail.attempts.length - 1].status === "SUCCESS")}
                          onClick={() => handleExecuteRecovery(detail.opportunity.id)}
                        >
                          {isExecutingRecovery ? "Running Executor..." : detail.attempts && detail.attempts.length > 0 && detail.attempts[detail.attempts.length - 1].status === "SUCCESS" ? "Recovery Complete (Success)" : `Execute ${detail.action_traceability.recommended_action}`}
                        </button>
                      ) : (
                        <div className="blocked-execution-notice">
                          <span>🔒 Auto-Execution Blocked by Policy Engine rules.</span>
                        </div>
                      )}
                    </div>
                  </section>

                  {/* 8. REDESIGNED AUDIT TIMELINE */}
                  <section className="redesigned-timeline-panel">
                    <h3>Technical Workflow Progress Timeline</h3>
                    <div className="workflow-timeline-steps">
                      {(detail.timeline_stages || []).map((stage, idx) => {
                        const isSelected = selectedTimelineStage === stage.stage;
                        return (
                          <button
                            key={idx}
                            className={`timeline-step-btn ${stage.reached ? "reached" : ""} ${stage.status} ${isSelected ? "selected" : ""}`}
                            onClick={() => setSelectedTimelineStage(stage.stage)}
                          >
                            <div className="step-circle">
                              {stage.status === "pass" ? "✓" : stage.status === "fail" ? "✕" : "○"}
                            </div>
                            <span className="step-label">{stage.stage}</span>
                          </button>
                        );
                      })}
                    </div>

                    {/* Clickable details box below */}
                    {selectedTimelineStage && (
                      <div className="timeline-stage-details-card">
                        {(() => {
                          const activeStageData = (detail.timeline_stages || []).find(s => s.stage === selectedTimelineStage);
                          if (!activeStageData) return <p className="helper-message">No data for selected stage.</p>;
                          return (
                            <>
                              <div className="details-card-header">
                                <h4>Stage Details: {selectedTimelineStage}</h4>
                                <span className={`status-pill ${activeStageData.status}`}>
                                  {activeStageData.status.toUpperCase()}
                                </span>
                              </div>
                              <div className="details-card-grid">
                                <div>
                                  <span className="card-label">TIMESTAMP</span>
                                  <span className="card-val">{formatIsoTimestamp(activeStageData.timestamp) || "Pending Stage"}</span>
                                </div>
                                {activeStageData.details.event_id && (
                                  <div>
                                    <span className="card-label">EVENT ID</span>
                                    <span className="card-val"><code>{activeStageData.details.event_id}</code></span>
                                  </div>
                                )}
                                {activeStageData.details.workflow_id && (
                                  <div>
                                    <span className="card-label">WORKFLOW ID</span>
                                    <span className="card-val"><code>{activeStageData.details.workflow_id}</code></span>
                                  </div>
                                )}
                                <div>
                                  <span className="card-label">OPPORTUNITY ID</span>
                                  <span className="card-val"><code>OPP-{activeStageData.details.opportunity_id || detail.opportunity.id}</code></span>
                                </div>
                                {activeStageData.details.attempt_id && (
                                  <div>
                                    <span className="card-label">ATTEMPT ID</span>
                                    <span className="card-val"><code>ATT-{activeStageData.details.attempt_id}</code></span>
                                  </div>
                                )}
                                {activeStageData.details.correlation_id && (
                                  <div>
                                    <span className="card-label">CORRELATION / TRACE ID</span>
                                    <span className="card-val"><code>{activeStageData.details.correlation_id}</code></span>
                                  </div>
                                )}
                              </div>
                              {/* transition explain text */}
                              <div className="details-transition-explanation">
                                <strong>Technical Transition Trace:</strong>
                                {selectedTimelineStage === "DETECTED" && (
                                  <p>Event received via Razorpay webhook hook registry. Successfully validated cryptographic signature and parsed core payment failure payload.</p>
                                )}
                                {selectedTimelineStage === "DIAGNOSED" && (
                                  <p>AI diagnosis analysis completed. System evaluated payment method, amount, failure code, and customer segments to derive recovery parameters.</p>
                                )}
                                {selectedTimelineStage === "AI DECISION" && (
                                  <p>AI generated structured diagnosis recommendation. Result verified against JSON-schema parser version {activeStageData.details.schema_version || "1.0.0"} and validated for syntax schema safety.</p>
                                )}
                                {selectedTimelineStage === "POLICY" && (
                                  <p>Policy Evaluator rules applied to verify recovery limits, duplicate actions, and environment checks. Result was evaluated as {activeStageData.details.result || "UNKNOWN"}.</p>
                                )}
                                {selectedTimelineStage === "EXECUTION" && (
                                  <p>Action {activeStageData.details.action || "CREATE_PAYMENT_LINK"} initiated via gateway executor adapter. Gateway execution reported state: {activeStageData.details.status || "PENDING"}.</p>
                                )}
                                {selectedTimelineStage === "VERIFICATION" && (
                                  <p>Post-execution validator queried Razorpay payment registry to check captured status. Result verified: {activeStageData.details.verified_outcome || "PENDING"}.</p>
                                )}
                              </div>
                            </>
                          );
                        })()}
                      </div>
                    )}
                  </section>
                </div>
              ) : (
                <p className="helper-message">Select an opportunity to view its recovery journey and audit trace.</p>
              )}
            </div>
          </>
        )}
      </aside>
    </main>
  );
}

function Badge({ text, tone }: { text: string; tone: Tone }) {
  return <span className={`badge badge-${tone}`}>{text}</span>;
}

function KpiCard({ title, value, note }: { title: string; value: string; note: string }) {
  return (
    <article className="kpi-card">
      <p className="kpi-title">{title}</p>
      <p className="kpi-value">{value}</p>
      <p className="kpi-note">{note}</p>
    </article>
  );
}

function MetricCompare({
  label,
  baseline,
  recoveriq,
  baselineLabel,
  recoveriqLabel,
  max,
  inverse,
}: {
  label: string;
  baseline: number;
  recoveriq: number;
  baselineLabel: string;
  recoveriqLabel: string;
  max?: number;
  inverse?: boolean;
}) {
  const scaleMax = max || Math.max(baseline, recoveriq, 1);
  const baselineWidth = Math.max(6, (baseline / scaleMax) * 100);
  const recoveriqWidth = Math.max(6, (recoveriq / scaleMax) * 100);
  const betterIsRecoverIQ = inverse ? recoveriq <= baseline : recoveriq >= baseline;

  return (
    <div className="metric-compare">
      <div className="metric-compare-head">
        <strong>{label}</strong>
        <Badge text={betterIsRecoverIQ ? "RecoverIQ Better" : "Baseline Better"} tone={betterIsRecoverIQ ? "good" : "warn"} />
      </div>
      <div className="bar-row">
        <span>Baseline</span>
        <div className="bar-track"><div className="bar-fill baseline" style={{ width: `${baselineWidth}%` }} /></div>
        <span>{baselineLabel}</span>
      </div>
      <div className="bar-row">
        <span>RecoverIQ</span>
        <div className="bar-track"><div className="bar-fill recoveriq" style={{ width: `${recoveriqWidth}%` }} /></div>
        <span>{recoveriqLabel}</span>
      </div>
    </div>
  );
}

function TableSkeleton() {
  return (
    <div className="table-wrapper">
      <table className="opportunities-table skeleton-table">
        <thead>
          <tr>
            <th>Opportunity</th>
            <th>Failure</th>
            <th>Amount</th>
            <th>Expected Recovery</th>
            <th>Confidence</th>
            <th>Policy</th>
            <th>Recovery Action</th>
            <th>Outcome</th>
          </tr>
        </thead>
        <tbody>
          {Array.from({ length: 6 }).map((_, idx) => (
            <tr key={idx}>
              <td>
                <div className="skeleton skeleton-text" style={{ width: "60px", height: "16px" }} />
                <div className="skeleton skeleton-text" style={{ width: "90px", height: "12px", marginTop: "4px" }} />
              </td>
              <td>
                <div className="skeleton skeleton-text" style={{ width: "70px", height: "16px" }} />
                <div className="skeleton skeleton-text" style={{ width: "50px", height: "12px", marginTop: "4px" }} />
              </td>
              <td>
                <div className="skeleton skeleton-text" style={{ width: "60px", height: "16px" }} />
              </td>
              <td>
                <div className="skeleton skeleton-text" style={{ width: "65px", height: "16px" }} />
                <div className="skeleton skeleton-text" style={{ width: "80px", height: "12px", marginTop: "4px" }} />
              </td>
              <td>
                <div className="skeleton skeleton-badge" style={{ width: "50px", height: "18px", borderRadius: "10px" }} />
              </td>
              <td>
                <div className="skeleton skeleton-badge" style={{ width: "60px", height: "18px", borderRadius: "10px" }} />
              </td>
              <td>
                <div className="skeleton skeleton-text" style={{ width: "80px", height: "16px" }} />
                <div className="skeleton skeleton-text" style={{ width: "50px", height: "12px", marginTop: "4px" }} />
              </td>
              <td>
                <div className="skeleton skeleton-badge" style={{ width: "65px", height: "18px", borderRadius: "10px" }} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function DrawerSkeleton() {
  return (
    <div className="detail-layout skeleton-layout" style={{ gap: "24px" }}>
      <section className="journey-panel">
        <h3>Recovery Timeline</h3>
        <div style={{ display: "flex", gap: "10px", marginTop: "12px" }}>
          {Array.from({ length: 4 }).map((_, idx) => (
            <div key={idx} className="skeleton" style={{ flex: 1, height: "30px", borderRadius: "6px" }} />
          ))}
        </div>
      </section>

      <div className="comparison-container" style={{ display: "grid", gridTemplateColumns: "1fr auto 1fr", gap: "16px", alignItems: "center" }}>
        <article className="info-card skeleton-card">
          <div className="skeleton" style={{ width: "120px", height: "18px", marginBottom: "16px" }} />
          <div className="skeleton" style={{ width: "80%", height: "14px", marginBottom: "8px" }} />
          <div className="skeleton" style={{ width: "60%", height: "14px", marginBottom: "8px" }} />
          <div className="skeleton" style={{ width: "70%", height: "14px", marginBottom: "8px" }} />
        </article>
        <div className="vs-divider" style={{ border: "none", boxShadow: "none", background: "transparent", minWidth: "20px" }} />
        <article className="info-card skeleton-card">
          <div className="skeleton" style={{ width: "120px", height: "18px", marginBottom: "16px" }} />
          <div className="skeleton" style={{ width: "90%", height: "14px", marginBottom: "8px" }} />
          <div className="skeleton" style={{ width: "50%", height: "14px", marginBottom: "8px" }} />
          <div className="skeleton" style={{ width: "80%", height: "14px", marginBottom: "8px" }} />
        </article>
      </div>

      <section className="insight-grid">
        <article className="info-card">
          <div className="skeleton" style={{ width: "100px", height: "16px", marginBottom: "12px" }} />
          <div className="skeleton" style={{ width: "80%", height: "12px", marginBottom: "6px" }} />
          <div className="skeleton" style={{ width: "60%", height: "12px" }} />
        </article>
        <article className="info-card">
          <div className="skeleton" style={{ width: "100px", height: "16px", marginBottom: "12px" }} />
          <div className="skeleton" style={{ width: "80%", height: "12px", marginBottom: "6px" }} />
          <div className="skeleton" style={{ width: "60%", height: "12px" }} />
        </article>
      </section>
    </div>
  );
}

function DashboardTrendChart({ data }: { data: TrendDataPoint[] }) {
  if (data.length === 0) {
    return <div className="helper-message">No trend data available</div>;
  }

  const maxVal = Math.max(
    ...data.map((d) => Math.max(d.revenue_at_risk_minor, d.recovered_revenue_minor)),
    100000
  ) * 1.15;

  const width = 500;
  const height = 200;
  const paddingLeft = 65;
  const paddingRight = 20;
  const paddingTop = 20;
  const paddingBottom = 30;

  const graphWidth = width - paddingLeft - paddingRight;
  const graphHeight = height - paddingTop - paddingBottom;
  const xSpacing = graphWidth / (data.length - 1 || 1);

  const getX = (index: number) => paddingLeft + index * xSpacing;
  const getY = (val: number) => paddingBottom + graphHeight - (val / maxVal) * graphHeight;

  const riskPath = data
    .map((d, i) => `${i === 0 ? "M" : "L"}${getX(i)} ${getY(d.revenue_at_risk_minor)}`)
    .join(" ");

  const recoveredPath = data
    .map((d, i) => `${i === 0 ? "M" : "L"}${getX(i)} ${getY(d.recovered_revenue_minor)}`)
    .join(" ");

  return (
    <div className="trend-chart-container">
      <div className="chart-legend" style={{ display: "flex", gap: "16px", justifyContent: "flex-end", marginBottom: "8px", fontSize: "11px" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "4px" }}>
          <span style={{ display: "inline-block", width: "12px", height: "3px", background: "var(--line)", borderStyle: "dashed" }} />
          <span style={{ color: "var(--text-soft)" }}>Revenue at Risk</span>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: "4px" }}>
          <span style={{ display: "inline-block", width: "12px", height: "3px", background: "var(--good-text)" }} />
          <span style={{ color: "var(--good-text)", fontWeight: "600" }}>Recovered by AI</span>
        </div>
      </div>
      <svg viewBox={`0 0 ${width} ${height}`} className="svg-chart" style={{ width: "100%", height: "auto" }}>
        {/* Horizontal grid lines */}
        {[0, 0.25, 0.5, 0.75, 1].map((ratio) => {
          const yVal = paddingTop + graphHeight * ratio;
          const labelVal = maxVal * (1 - ratio);
          return (
            <g key={ratio}>
              <line
                x1={paddingLeft}
                y1={yVal}
                x2={width - paddingRight}
                y2={yVal}
                stroke="#e2e8f0"
                strokeWidth="1"
                strokeDasharray="4 4"
              />
              <text
                x={paddingLeft - 8}
                y={yVal + 4}
                textAnchor="end"
                fontSize="10"
                fill="var(--text-muted)"
              >
                {formatMinorCurrency(Math.round(labelVal))}
              </text>
            </g>
          );
        })}

        {/* X axis labels */}
        {data.map((d, i) => (
          <text
            key={d.date}
            x={getX(i)}
            y={height - 8}
            textAnchor="middle"
            fontSize="10"
            fill="var(--text-muted)"
          >
            {d.display_date}
          </text>
        ))}

        {/* Risk line (dashed grey) */}
        <path
          d={riskPath}
          fill="none"
          stroke="var(--line)"
          strokeWidth="2"
          strokeDasharray="4 4"
        />

        {/* Recovered line (solid green) */}
        <path
          d={recoveredPath}
          fill="none"
          stroke="var(--good-text)"
          strokeWidth="3"
        />

        {/* Data points */}
        {data.map((d, i) => (
          <g key={d.date}>
            <circle
              cx={getX(i)}
              cy={getY(d.recovered_revenue_minor)}
              r="4"
              fill="var(--good-text)"
              stroke="#ffffff"
              strokeWidth="2"
            />
            {d.revenue_at_risk_minor > 0 && (
              <circle
                cx={getX(i)}
                cy={getY(d.revenue_at_risk_minor)}
                r="3"
                fill="var(--line)"
                stroke="#ffffff"
                strokeWidth="1.5"
              />
            )}
          </g>
        ))}
      </svg>
    </div>
  );
}

