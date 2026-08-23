import { useEffect, useMemo, useState, type CSSProperties } from "react";
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
  };
  error?: { code?: string; message?: string };
};

type Tone = "good" | "warn" | "bad" | "neutral";

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

const DEFAULT_BUTTON_STYLE: CSSProperties = {
  border: "1px solid transparent",
  borderRadius: 10,
  padding: "9px 14px",
  cursor: "pointer",
  fontWeight: 600,
};

function formatMinorCurrency(minorUnits: number): string {
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 2,
  }).format(minorUnits / 100);
}

function formatPercent(decimalFraction: number): string {
  return `${(decimalFraction * 100).toFixed(1)}%`;
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
  const [opportunities, setOpportunities] = useState<OpportunityListItem[]>([]);
  const [selectedOpportunityId, setSelectedOpportunityId] = useState<number | null>(null);
  const [detail, setDetail] = useState<OpportunityDetail | null>(null);

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
      setSelectedOpportunityId(payload.data.items[0].id);
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
      setTimelineCollapsed({});
    } finally {
      setIsDetailLoading(false);
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
    const response = await fetch("/api/v1/failure-demos/trigger", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ scenario_id: scenarioId }),
    });
    const payload = (await response.json()) as { success?: boolean; error?: { code?: string; message?: string } };
    if (response.ok && payload.success) {
      setFailureScenarioResult(`Scenario ${scenarioId} returned success response.`);
      return;
    }
    setFailureScenarioResult(
      `Scenario ${scenarioId} -> ${payload.error?.code || "ERROR"}: ${payload.error?.message || "Request failed."}`,
    );
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
    try {
      await Promise.all([loadSummary(), loadOpportunities(false), loadEvaluationHistory(), loadFailureScenarios(), loadRazorpayStatus()]);
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
            <p className="hero-copy">Recover revenue that would otherwise be lost.</p>
            <p className="hero-flow">Detect {"->"} Diagnose {"->"} Decide {"->"} Recover {"->"} Verify</p>
          </div>
          <div className="hero-actions">
            <div className="mode-chip">{modeLabel}</div>
            <button onClick={loadCommandCenter} className="btn btn-primary" style={DEFAULT_BUTTON_STYLE}>
              Refresh
            </button>
            <button
              onClick={() => runDemoMutation("/api/v1/demo/seed-core-recovery")}
              className="btn btn-secondary"
              style={{ ...DEFAULT_BUTTON_STYLE, opacity: isDemoMutating ? 0.7 : 1 }}
              disabled={isDemoMutating}
            >
              Seed State
            </button>
            <button
              onClick={() => runDemoMutation("/api/v1/demo/reset-core-recovery")}
              className="btn btn-tertiary"
              style={{ ...DEFAULT_BUTTON_STYLE, opacity: isDemoMutating ? 0.7 : 1 }}
              disabled={isDemoMutating}
            >
              Empty State
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

        <section className="panel health-panel">
          <h2>Operating Health</h2>
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
          {demoMutationMessage ? <p className="helper-message">{demoMutationMessage}</p> : null}
        </section>

        {isLoading ? (
          <section className="panel loading-panel">
            <h2>Loading command center</h2>
            <p>Fetching live metrics, opportunities, and evaluation telemetry.</p>
          </section>
        ) : null}

        {!isLoading && error ? (
          <section className="panel error-panel">
            <h2>Unable to load data</h2>
            <p>{error}</p>
            <button onClick={loadCommandCenter} className="btn btn-danger" style={DEFAULT_BUTTON_STYLE}>
              Retry
            </button>
          </section>
        ) : null}

        {!isLoading && !error && summary ? (
          <>
            <section className="panel">
              <h2>Revenue Recovery Snapshot</h2>
              <p className="panel-copy">Live business indicators from the active operating mode.</p>
              {isEmptySummary(summary) ? (
                <div className="empty-state">
                  <h3>No active revenue recovery yet</h3>
                  <p>Use Seed State to load opportunities, or wait for failed payments to enter the recovery workflow.</p>
                </div>
              ) : (
                <div className="kpi-grid">
                  <KpiCard title="Revenue At Risk" value={formatMinorCurrency(summary.revenue_at_risk_minor)} note="Total failed-payment exposure" />
                  <KpiCard title="Recoverable Revenue" value={formatMinorCurrency(summary.recoverable_revenue_minor)} note="Policy-eligible exposure" />
                  <KpiCard title="Recovered Revenue" value={formatMinorCurrency(summary.gross_recovered_minor)} note={`Coverage ${formatPercent(recoveredCoverage)}`} />
                  <KpiCard title="Recovery Rate" value={formatPercent(summary.recovery_rate)} note="Recovered / recoverable" />
                  <KpiCard title="Active Opportunities" value={String(summary.active_opportunities)} note="Open recovery workflows" />
                  <KpiCard title="Recovery Attempts" value={String(summary.recovery_attempts)} note="Total attempts executed" />
                </div>
              )}
            </section>

            <section className="workspace-grid">
              <article className="panel detail-primary">
                <h2>Opportunity Detail</h2>
                <p className="panel-copy">Primary recovery workflow view from failed payment to verified outcome.</p>

                {!selectedItem ? (
                  <div className="empty-state">
                    <h3>No opportunity selected</h3>
                    <p>Select an opportunity to inspect AI diagnosis, policy authorization, payment action, and audit trace.</p>
                  </div>
                ) : null}

                {selectedItem && isDetailLoading ? <p className="helper-message">Loading opportunity detail...</p> : null}

                {selectedItem && detail && !isDetailLoading ? (
                  <div className="detail-layout">
                    <section className="journey-panel">
                      <h3>Recovery Timeline</h3>
                      <div className="journey-track" aria-label="Recovery timeline">
                        {JOURNEY_STAGES.map((stage, index) => {
                          const reached = journeyState?.reached[index] || false;
                          const active = (journeyState?.activeIndex || 0) === index;
                          return (
                            <div key={stage} className={`journey-stage ${reached ? "reached" : ""} ${active ? "active" : ""}`}>
                              <span>{stage}</span>
                              {index < JOURNEY_STAGES.length - 1 ? <span className="journey-arrow">↓</span> : null}
                            </div>
                          );
                        })}
                      </div>
                      <p className="helper-message">
                        Current state: <strong>{toTitle(detail.recovery_state.current || "pending")}</strong>
                      </p>
                    </section>

                    <section className="insight-grid">
                      <article className="info-card">
                        <h3>AI Explanation</h3>
                        <p><strong>Diagnosis:</strong> {detail.evidence.diagnosis || "-"}</p>
                        <p><strong>Evidence:</strong> {detail.evidence.decision_source || "Model signal unavailable"}</p>
                        <p><strong>Confidence:</strong> {formatPercent(detail.opportunity.confidence)}</p>
                        <p><strong>Recommended Action:</strong> {detail.action_traceability.recommended_action || "-"}</p>
                      </article>

                      <article className="info-card">
                        <h3>Deterministic Policy</h3>
                        <p className={`policy-decision ${policyDecision === "ALLOW" ? "allow" : policyDecision === "BLOCK" ? "block" : "pending"}`}>
                          POLICY: {policyDecision}
                        </p>
                        <div className="check-grid">
                          {Object.entries(detail.policy_checks.checks).map(([key, passed]) => (
                            <div key={key} className="check-item">
                              <span>{getPolicyCheckLabel(key)}</span>
                              <span className={passed ? "check-pass" : "check-fail"}>{passed ? "✓" : "✕"}</span>
                            </div>
                          ))}
                          {Object.keys(detail.policy_checks.checks).length === 0 ? <p className="helper-message">No policy checks reported.</p> : null}
                        </div>
                        <p className="helper-message">Execution is authorized by policy controls, not by AI recommendation.</p>
                      </article>

                      <article className="info-card">
                        <h3>Razorpay Payment Link</h3>
                        {latestAttemptWithLink?.payment_link ? (
                          <>
                            <p><strong>Payment Link ID:</strong> {latestAttemptWithLink.payment_link.payment_link_id}</p>
                            <p><strong>Status:</strong> {latestAttemptWithLink.payment_link.status}</p>
                            <p><strong>Reference:</strong> {latestAttemptWithLink.payment_link.payment_link_reference_id}</p>
                            {paymentLinkUrl ? (
                              <a href={paymentLinkUrl} target="_blank" rel="noreferrer" className="pay-link">
                                Open Payment Link
                              </a>
                            ) : (
                              <p className="helper-message">Payment link URL is not exposed by this detail payload.</p>
                            )}
                          </>
                        ) : (
                          <p className="helper-message">No Razorpay payment link created for the selected opportunity yet.</p>
                        )}
                      </article>

                      <article className="info-card">
                        <h3>Outcome</h3>
                        <p><strong>Outcome Status:</strong> {detail.semantic_states?.business_outcome || detail.action_traceability.latest_verified_outcome || "NOT_RECOVERED"}</p>
                        <p><strong>Recovered Revenue:</strong> {formatMinorCurrency(detail.economics.gross_recovered_minor)}</p>
                        <p><strong>Net Recovered:</strong> {formatMinorCurrency(detail.economics.net_recovered_minor)}</p>
                        <p><strong>Attempts:</strong> {detail.action_traceability.attempt_count}</p>
                      </article>
                    </section>

                    <section className="audit-panel">
                      <h3>Audit Timeline</h3>
                      {detail.timeline_groups.length === 0 ? (
                        <p className="helper-message">No audit events available.</p>
                      ) : (
                        <div className="audit-group-list">
                          {detail.timeline_groups.map((group) => {
                            const isCollapsed = timelineCollapsed[group.group] || false;
                            return (
                              <article key={group.group} className="audit-group">
                                <header>
                                  <div>
                                    <strong>{group.group}</strong>
                                    <div className="badge-row">
                                      <Badge text={`PASS ${group.counts.pass}`} tone="good" />
                                      <Badge text={`FAIL ${group.counts.fail}`} tone="bad" />
                                      <Badge text={`PENDING ${group.counts.pending}`} tone="warn" />
                                    </div>
                                  </div>
                                  <button
                                    onClick={() => setTimelineCollapsed((prev) => ({ ...prev, [group.group]: !isCollapsed }))}
                                    className="btn btn-inline"
                                    style={DEFAULT_BUTTON_STYLE}
                                  >
                                    {isCollapsed ? "Expand" : "Collapse"}
                                  </button>
                                </header>
                                {!isCollapsed ? (
                                  <div className="audit-event-list">
                                    {group.events.map((event, index) => (
                                      <details key={`${group.group}-${index}`} className="audit-event">
                                        <summary>
                                          <Badge
                                            text={event.outcome_status.toUpperCase()}
                                            tone={event.outcome_status === "pass" ? "good" : event.outcome_status === "fail" ? "bad" : "warn"}
                                          />
                                          <span>{event.event_type}</span>
                                          <span>{formatIsoTimestamp(event.timestamp)}</span>
                                        </summary>
                                        <div>
                                          <p><strong>Actor:</strong> {event.actor_type}</p>
                                          <p><strong>Stage:</strong> {event.stage || "-"}</p>
                                          <p><strong>Reason:</strong> {event.reason || "-"}</p>
                                          <pre>{serializeEvidence(event.outcome || {})}</pre>
                                        </div>
                                      </details>
                                    ))}
                                  </div>
                                ) : null}
                              </article>
                            );
                          })}
                        </div>
                      )}
                    </section>
                  </div>
                ) : null}
              </article>

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
                    <button onClick={() => { setOpportunityPage(1); setSearchFilter(searchInput); }} className="btn btn-primary" style={DEFAULT_BUTTON_STYLE}>
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
                      style={DEFAULT_BUTTON_STYLE}
                    >
                      Reset
                    </button>
                  </div>
                </div>

                {isOpportunityLoading ? <p className="helper-message">Refreshing opportunities...</p> : null}

                {opportunities.length === 0 ? (
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
                                  <Badge text={formatPercent(item.confidence)} tone={toToneForRisk(item.risk_bucket)} />
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
                      style={DEFAULT_BUTTON_STYLE}
                    >
                      Prev
                    </button>
                    <button
                      onClick={() => setOpportunityPage((prev) => prev + 1)}
                      disabled={!opportunityHasNext}
                      className="btn btn-inline"
                      style={DEFAULT_BUTTON_STYLE}
                    >
                      Next
                    </button>
                  </div>
                </div>
              </article>
            </section>

            <section className="panel">
              <h2>Evaluation</h2>
              <p className="panel-copy">Baseline vs RecoverIQ for precision, recall, F1, false-positive cost, and revenue recovered.</p>

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
                  style={{ ...DEFAULT_BUTTON_STYLE, opacity: isRunSubmitting ? 0.7 : 1 }}
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
                          <span>{`F1 ${formatPercent(item.f1)} | Records ${item.records}`}</span>
                          <span>{formatIsoTimestamp(item.last_created_at || null)}</span>
                        </button>
                      ))}
                    </div>
                  )}
                </article>

                <article className="evaluation-main">
                  <h3>Baseline vs RecoverIQ</h3>
                  {isEvaluationLoading ? <p className="helper-message">Loading evaluation insights...</p> : null}
                  {!isEvaluationLoading && !evaluationComparison ? <p className="helper-message">Select an evaluation run to inspect metrics.</p> : null}

                  {!isEvaluationLoading && evaluationComparison ? (
                    <>
                      <div className="metric-compare-grid">
                        <MetricCompare
                          label="Precision"
                          baseline={evaluationComparison.baseline.precision}
                          recoveriq={evaluationComparison.recoveriq.precision}
                          baselineLabel={formatPercent(evaluationComparison.baseline.precision)}
                          recoveriqLabel={formatPercent(evaluationComparison.recoveriq.precision)}
                        />
                        <MetricCompare
                          label="Recall"
                          baseline={evaluationComparison.baseline.recall}
                          recoveriq={evaluationComparison.recoveriq.recall}
                          baselineLabel={formatPercent(evaluationComparison.baseline.recall)}
                          recoveriqLabel={formatPercent(evaluationComparison.recoveriq.recall)}
                        />
                        <MetricCompare
                          label="F1"
                          baseline={evaluationComparison.baseline.f1}
                          recoveriq={evaluationComparison.recoveriq.f1}
                          baselineLabel={formatPercent(evaluationComparison.baseline.f1)}
                          recoveriqLabel={formatPercent(evaluationComparison.recoveriq.f1)}
                        />
                        <MetricCompare
                          label="Recovery Rate"
                          baseline={evaluationComparison.baseline.recovery_rate}
                          recoveriq={evaluationComparison.recoveriq.recovery_rate}
                          baselineLabel={formatPercent(evaluationComparison.baseline.recovery_rate)}
                          recoveriqLabel={formatPercent(evaluationComparison.recoveriq.recovery_rate)}
                        />
                        <MetricCompare
                          label="Revenue Recovered"
                          baseline={evaluationComparison.baseline.gross_recovered_minor}
                          recoveriq={evaluationComparison.recoveriq.gross_recovered_minor}
                          baselineLabel={formatMinorCurrency(evaluationComparison.baseline.gross_recovered_minor)}
                          recoveriqLabel={formatMinorCurrency(evaluationComparison.recoveriq.gross_recovered_minor)}
                          max={Math.max(evaluationComparison.baseline.gross_recovered_minor, evaluationComparison.recoveriq.gross_recovered_minor, 1)}
                        />
                        <MetricCompare
                          label="False-positive Cost"
                          baseline={evaluationComparison.baseline.false_positive_exposure_minor}
                          recoveriq={evaluationComparison.recoveriq.false_positive_exposure_minor}
                          baselineLabel={formatMinorCurrency(evaluationComparison.baseline.false_positive_exposure_minor)}
                          recoveriqLabel={formatMinorCurrency(evaluationComparison.recoveriq.false_positive_exposure_minor)}
                          max={Math.max(evaluationComparison.baseline.false_positive_exposure_minor, evaluationComparison.recoveriq.false_positive_exposure_minor, 1)}
                          inverse
                        />
                      </div>

                      {evaluationDrilldown ? (
                        <div className="drilldown-row">
                          <p>
                            <strong>Confusion Matrix:</strong> TP {evaluationDrilldown.confusion_matrix.tp} | FP {evaluationDrilldown.confusion_matrix.fp} | FN {evaluationDrilldown.confusion_matrix.fn} | TN {evaluationDrilldown.confusion_matrix.tn}
                          </p>
                          <p>
                            <strong>False-positive Exposure:</strong> {formatMinorCurrency(evaluationDrilldown.false_positive_cost.financial_exposure_minor)}
                          </p>
                        </div>
                      ) : null}
                    </>
                  ) : null}
                </article>
              </div>
            </section>

            <section className="panel secondary-panel">
              <h2>Reliability & Security</h2>
              <p className="panel-copy">Controlled failure scenarios and readiness checks for safe operation.</p>

              <div className="reliability-grid">
                <article>
                  <h3>Failure Scenarios</h3>
                  {failureScenarios.length === 0 ? (
                    <p className="helper-message">No failure scenarios available.</p>
                  ) : (
                    <div className="scenario-list">
                      {failureScenarios.map((scenario) => (
                        <div key={scenario.scenario_id} className="scenario-item">
                          <div>
                            <p className="row-title">{scenario.title}</p>
                            <p className="row-subtitle">{scenario.description}</p>
                            <p className="row-subtitle">Expected: {scenario.expected_behavior || scenario.expected_error_code}</p>
                          </div>
                          <button onClick={() => triggerFailureScenario(scenario.scenario_id)} className="btn btn-inline" style={DEFAULT_BUTTON_STYLE}>
                            Trigger
                          </button>
                        </div>
                      ))}
                    </div>
                  )}
                  {failureScenarioResult ? <p className="helper-message">{failureScenarioResult}</p> : null}
                </article>

                <article>
                  <h3>Readiness</h3>
                  <button
                    onClick={executeReadinessValidation}
                    disabled={isReadinessRunning}
                    className="btn btn-primary"
                    style={{ ...DEFAULT_BUTTON_STYLE, opacity: isReadinessRunning ? 0.7 : 1 }}
                  >
                    {isReadinessRunning ? "Running workflow..." : "Run Readiness Workflow"}
                  </button>

                  {readinessValidation ? (
                    <div className="readiness-list">
                      <div className="badge-row">
                        <Badge
                          text={readinessValidation.status}
                          tone={readinessValidation.status === "PASS" ? "good" : readinessValidation.status === "FAIL" ? "bad" : "warn"}
                        />
                        <span>{`Pass ${readinessValidation.summary.pass_count} | Partial ${readinessValidation.summary.partial_count} | Fail ${readinessValidation.summary.fail_count}`}</span>
                      </div>
                      {readinessValidation.checks.map((check) => (
                        <div key={check.id} className="readiness-item">
                          <div className="badge-row">
                            <Badge text={check.status} tone={check.status === "PASS" ? "good" : check.status === "FAIL" ? "bad" : "warn"} />
                            <strong>{check.id}</strong>
                          </div>
                          <p>{check.message}</p>
                        </div>
                      ))}
                    </div>
                  ) : null}
                </article>
              </div>
            </section>
          </>
        ) : null}
      </section>
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
