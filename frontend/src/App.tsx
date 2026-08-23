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
  audit_trail: Array<{
    timestamp: string | null;
    event_type: string;
    stage: string | null;
    outcome_status: "pass" | "fail" | "pending";
    reason: string | null;
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
    pagination_mode?: "page" | "cursor";
    cursor?: string | null;
    next_cursor?: string | null;
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

const buttonStyle: CSSProperties = {
  background: "#0f172a",
  color: "#ffffff",
  border: "1px solid transparent",
  borderRadius: 9,
  padding: "9px 13px",
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
    return "-";
  }
  return value.toLocaleString("en-IN", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatPercentValue(value: number): string {
  if (!Number.isFinite(value)) {
    return "0.0%";
  }
  return `${value.toFixed(1)}%`;
}

function toDeltaClass(delta: number): string {
  return delta >= 0 ? "delta-positive" : "delta-negative";
}

function toDeltaLabel(delta: number): string {
  return `${delta >= 0 ? "+" : ""}${delta.toFixed(1)}%`;
}

function toRiskTone(bucket: string): "high" | "medium" | "low" | "neutral" {
  const normalized = bucket.toUpperCase();
  if (normalized === "HIGH") return "high";
  if (normalized === "MEDIUM") return "medium";
  if (normalized === "LOW") return "low";
  return "neutral";
}

function toPolicyTone(value: string | null): "pass" | "fail" | "pending" {
  const normalized = (value || "").toUpperCase();
  if (normalized.includes("ALLOW") || normalized.includes("APPROV")) return "pass";
  if (normalized.includes("BLOCK") || normalized.includes("FAIL")) return "fail";
  return "pending";
}

function toOutcomeTone(value: string | null): "pass" | "fail" | "pending" {
  const normalized = (value || "").toUpperCase();
  if (["SUCCESS", "RECOVERED", "CAPTURED", "PASS"].some((item) => normalized.includes(item))) return "pass";
  if (["FAILED", "FAIL", "BLOCKED", "CANCELLED"].some((item) => normalized.includes(item))) return "fail";
  return "pending";
}

function serializeEvidence(value: unknown): string {
  try {
    return JSON.stringify(value);
  } catch {
    return "{}";
  }
}

function formatReasonCodes(codes: string[], limit = 3): string {
  if (codes.length === 0) {
    return "-";
  }
  if (codes.length <= limit) {
    return codes.join(", ");
  }
  return `${codes.slice(0, limit).join(", ")} +${codes.length - limit} more`;
}

function parseNumber(input: string, fallback: number): number {
  const parsed = Number.parseInt(input, 10);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function isEmptySummary(summary: Summary): boolean {
  return (
    summary.revenue_at_risk_minor === 0 &&
    summary.recoverable_revenue_minor === 0 &&
    summary.gross_recovered_minor === 0 &&
    summary.active_opportunities === 0
  );
}

export function App() {
  const [summary, setSummary] = useState<Summary | null>(null);
  const [opportunities, setOpportunities] = useState<OpportunityListItem[]>([]);
  const [selectedOpportunityId, setSelectedOpportunityId] = useState<number | null>(null);
  const [detail, setDetail] = useState<OpportunityDetail | null>(null);

  const [statusFilter, setStatusFilter] = useState<string>("ALL");
  const [actionFilter, setActionFilter] = useState<string>("ALL");
  const [riskBucketFilter, setRiskBucketFilter] = useState<string>("ALL");
  const [sortBy, setSortBy] = useState<string>("updated_desc");
  const [searchInput, setSearchInput] = useState<string>("");
  const [searchFilter, setSearchFilter] = useState<string>("");
  const [opportunityPaginationMode, setOpportunityPaginationMode] = useState<"page" | "cursor">("page");
  const [opportunityPage, setOpportunityPage] = useState<number>(1);
  const [opportunityPageSize, setOpportunityPageSize] = useState<number>(20);
  const [opportunityTotalCount, setOpportunityTotalCount] = useState<number>(0);
  const [opportunityTotalPages, setOpportunityTotalPages] = useState<number>(1);
  const [opportunityHasNext, setOpportunityHasNext] = useState<boolean>(false);
  const [opportunityHasPrev, setOpportunityHasPrev] = useState<boolean>(false);
  const [opportunityCursor, setOpportunityCursor] = useState<string | null>(null);
  const [opportunityNextCursor, setOpportunityNextCursor] = useState<string | null>(null);
  const [opportunityCursorHistory, setOpportunityCursorHistory] = useState<string[]>([]);
  const [cursorHelperMessage, setCursorHelperMessage] = useState<string>("");
  const [timelineCollapsedByOpportunity, setTimelineCollapsedByOpportunity] = useState<Record<number, Record<string, boolean>>>({});

  const [evaluationHistory, setEvaluationHistory] = useState<EvaluationSummary[]>([]);
  const [selectedEvaluationRunId, setSelectedEvaluationRunId] = useState<string | null>(null);
  const [evaluationComparison, setEvaluationComparison] = useState<EvaluationComparisonResponse["data"] | null>(null);
  const [evaluationDrilldown, setEvaluationDrilldown] = useState<EvaluationDrilldownResponse["data"] | null>(null);
  const [isEvaluationLoading, setIsEvaluationLoading] = useState<boolean>(false);
  const [isRunSubmitting, setIsRunSubmitting] = useState<boolean>(false);
  const [runDatasetVersion, setRunDatasetVersion] = useState<string>("phase11_dataset");
  const [runSplit, setRunSplit] = useState<string>("TEST");
  const [runGenerationSeed, setRunGenerationSeed] = useState<string>("42");
  const [runTotalCases, setRunTotalCases] = useState<string>("1000");
  const [failureScenarios, setFailureScenarios] = useState<FailureScenario[]>([]);
  const [failureScenarioResult, setFailureScenarioResult] = useState<string>("");
  const [readinessValidation, setReadinessValidation] = useState<ReadinessValidationResponse["data"] | null>(null);
  const [isReadinessRunning, setIsReadinessRunning] = useState<boolean>(false);
  const [razorpayStatus, setRazorpayStatus] = useState<RazorpayStatusResponse["data"] | null>(null);
  const [demoMutationMessage, setDemoMutationMessage] = useState<string>("");
  const [isDemoMutating, setIsDemoMutating] = useState<boolean>(false);

  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [isOpportunityLoading, setIsOpportunityLoading] = useState<boolean>(false);
  const [isDetailLoading, setIsDetailLoading] = useState<boolean>(false);
  const [autoRefreshEnabled, setAutoRefreshEnabled] = useState<boolean>(false);
  const [viewportWidth, setViewportWidth] = useState<number>(window.innerWidth);

  useEffect(() => {
    const onResize = () => setViewportWidth(window.innerWidth);
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);

  const isTabletOrLower = viewportWidth < 1024;
  const isMobile = viewportWidth < 768;

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

  const runDemoMutation = async (endpoint: "/api/v1/demo/reset-core-recovery" | "/api/v1/demo/seed-core-recovery") => {
    setIsDemoMutating(true);
    setDemoMutationMessage("");
    try {
      const response = await fetch(endpoint, { method: "POST" });
      const payload = (await response.json()) as { success?: boolean; error?: { message?: string } };
      if (!response.ok || !payload.success) {
        throw new Error(payload.error?.message || "Demo operation failed.");
      }
      setDemoMutationMessage(endpoint.includes("reset") ? "Demo reset complete." : "Demo seed complete.");
      await loadCommandCenter();
    } finally {
      setIsDemoMutating(false);
    }
  };

  const loadOpportunities = async (showLoader: boolean) => {
    if (showLoader) {
      setIsOpportunityLoading(true);
    }
    const query = new URLSearchParams();
    query.set("pagination_mode", opportunityPaginationMode);
    query.set("page", String(opportunityPage));
    query.set("page_size", String(opportunityPageSize));
    query.set("sort_by", sortBy);
    if (opportunityPaginationMode === "cursor" && opportunityCursor) {
      query.set("cursor", opportunityCursor);
    }
    if (statusFilter !== "ALL") {
      query.set("status", statusFilter);
    }
    if (actionFilter !== "ALL") {
      query.set("action", actionFilter);
    }
    if (riskBucketFilter !== "ALL") {
      query.set("risk_bucket", riskBucketFilter.toLowerCase());
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
    setOpportunityNextCursor(payload.data.next_cursor || null);
    if (payload.data.items.length === 0) {
      setSelectedOpportunityId(null);
      setDetail(null);
      setOpportunityNextCursor(null);
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

  const resetCursorPagination = () => {
    setOpportunityCursor(null);
    setOpportunityNextCursor(null);
    setOpportunityCursorHistory([]);
    setOpportunityPage(1);
    setCursorHelperMessage("");
  };

  const buildCursorShareUrl = (cursorToken: string | null): string => {
    const params = new URLSearchParams();
    params.set("pagination_mode", "cursor");
    params.set("page_size", String(opportunityPageSize));
    params.set("sort_by", sortBy);
    if (statusFilter !== "ALL") {
      params.set("status", statusFilter);
    }
    if (actionFilter !== "ALL") {
      params.set("action", actionFilter);
    }
    if (riskBucketFilter !== "ALL") {
      params.set("risk_bucket", riskBucketFilter.toLowerCase());
    }
    if (searchFilter.trim().length > 0) {
      params.set("search", searchFilter.trim());
    }
    if (cursorToken) {
      params.set("cursor", cursorToken);
    }
    return `${window.location.origin}${window.location.pathname}?${params.toString()}`;
  };

  const copyTextToClipboard = async (value: string) => {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(value);
      return;
    }

    const textArea = document.createElement("textarea");
    textArea.value = value;
    textArea.style.position = "fixed";
    textArea.style.opacity = "0";
    document.body.appendChild(textArea);
    textArea.focus();
    textArea.select();
    document.execCommand("copy");
    document.body.removeChild(textArea);
  };

  const handleCopyCursorToken = async () => {
    const token = opportunityCursor || opportunityNextCursor;
    if (!token) {
      setCursorHelperMessage("No cursor token available for this page.");
      return;
    }

    try {
      await copyTextToClipboard(token);
      setCursorHelperMessage("Cursor token copied.");
    } catch {
      setCursorHelperMessage("Unable to copy cursor token in this browser.");
    }
  };

  const handleShareCursorLink = async () => {
    const shareUrl = buildCursorShareUrl(opportunityCursor);
    try {
      if (navigator.share) {
        await navigator.share({ title: "RecoverIQ Cursor Session", url: shareUrl });
        setCursorHelperMessage("Cursor session link shared.");
        return;
      }

      await copyTextToClipboard(shareUrl);
      setCursorHelperMessage("Cursor session link copied.");
    } catch {
      setCursorHelperMessage("Unable to share cursor link in this browser.");
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
      const payload = {
        dataset_version: runDatasetVersion,
        split: runSplit,
        generation_seed: parseNumber(runGenerationSeed, 42),
        // Prompt 04 default: held-out runs are configured for >=1000 synthetic cases.
        total_cases: parseNumber(runTotalCases, 1000),
        generate_if_missing: true,
      };
      const response = await fetch("/api/v1/evaluation/run", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(payload),
      });
      const runPayload = (await response.json()) as EvaluationRunResponse;
      if (!response.ok || !runPayload.success || !runPayload.data) {
        throw new Error(runPayload.error?.message || "Unable to run evaluation.");
      }

      const runId = runPayload.data.evaluation_run_id;
      setSelectedEvaluationRunId(runId);
      await loadEvaluationHistory();
      await loadEvaluationRunInsights(runId);
    } finally {
      setIsRunSubmitting(false);
    }
  };

  const loadCommandCenter = () => {
    setIsLoading(true);
    setError(null);

    Promise.all([loadSummary(), loadOpportunities(false), loadEvaluationHistory(), loadFailureScenarios(), loadRazorpayStatus()])
      .catch((fetchError: Error) => {
        setError(fetchError.message || "Unable to load command center data.");
      })
      .finally(() => setIsLoading(false));
  };

  useEffect(() => {
    loadCommandCenter();
  }, []);

  useEffect(() => {
    loadOpportunities(true).catch((fetchError: Error) => {
      setError(fetchError.message || "Unable to load opportunities.");
    });
  }, [
    statusFilter,
    actionFilter,
    riskBucketFilter,
    sortBy,
    searchFilter,
    opportunityPage,
    opportunityPageSize,
    opportunityPaginationMode,
    opportunityCursor,
  ]);

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
      if (selectedEvaluationRunId) {
        loadEvaluationRunInsights(selectedEvaluationRunId).catch(() => undefined);
      }
    }, 15000);
    return () => window.clearInterval(intervalId);
  }, [autoRefreshEnabled, selectedOpportunityId, selectedEvaluationRunId]);

  const selectedItem = useMemo(
    () => opportunities.find((item) => item.id === selectedOpportunityId) ?? null,
    [opportunities, selectedOpportunityId],
  );

  const selectedTimelineCollapseState = useMemo(() => {
    if (!selectedOpportunityId) {
      return {} as Record<string, boolean>;
    }
    return timelineCollapsedByOpportunity[selectedOpportunityId] || {};
  }, [selectedOpportunityId, timelineCollapsedByOpportunity]);

  const updateSelectedTimelineCollapseState = (nextState: Record<string, boolean>) => {
    if (!selectedOpportunityId) {
      return;
    }
    setTimelineCollapsedByOpportunity((prev) => ({
      ...prev,
      [selectedOpportunityId]: nextState,
    }));
  };

  const modeTone = summary?.mode === "razorpay_test" ? "#075985" : "#065f46";
  const modeBadgeBackground = summary?.mode === "razorpay_test" ? "#e0f2fe" : "#dcfce7";
  const recoveredCoverage = summary && summary.recoverable_revenue_minor > 0
    ? summary.gross_recovered_minor / summary.recoverable_revenue_minor
    : 0;

  return (
    <main className="app-shell">
      <section className="app-container">
        <header className="header-row">
          <div>
            <h1 className="header-title">RecoverIQ Command Center</h1>
            <p className="header-subtitle">
              Revenue recovery operations view for AI diagnosis, deterministic policy execution, and payment outcome verification.
            </p>
          </div>
          <div className="action-row">
            <button onClick={loadCommandCenter} style={buttonStyle} className="btn">
              Refresh Now
            </button>
            <button
              onClick={() => runDemoMutation("/api/v1/demo/reset-core-recovery")}
              disabled={isDemoMutating}
              style={{ ...buttonStyle, background: "#334155", opacity: isDemoMutating ? 0.7 : 1 }}
              className="btn btn-secondary"
            >
              Reset Demo
            </button>
            <button
              onClick={() => runDemoMutation("/api/v1/demo/seed-core-recovery")}
              disabled={isDemoMutating}
              style={{ ...buttonStyle, background: "#0f766e", opacity: isDemoMutating ? 0.7 : 1 }}
              className="btn btn-accent"
            >
              Seed Demo
            </button>
            <label style={{ display: "flex", gap: 8, alignItems: "center", color: "#334155", fontSize: 13 }}>
              <input
                type="checkbox"
                checked={autoRefreshEnabled}
                onChange={(event) => setAutoRefreshEnabled(event.target.checked)}
              />
              Auto-refresh (15s)
            </label>
          </div>
        </header>

        {demoMutationMessage ? (
          <section className="panel" style={{ marginBottom: 12 }}>
            <p className="meta">{demoMutationMessage}</p>
          </section>
        ) : null}

        {isLoading ? (
          <section className="panel">
            <h3 className="section-title">Loading command center</h3>
            <p className="section-subtitle">Fetching live operational metrics and workflow detail...</p>
          </section>
        ) : null}

        {!isLoading && error ? (
          <section className="panel alert-error">
            <p style={{ marginTop: 0 }}>{error}</p>
            <button onClick={loadCommandCenter} className="btn" style={{ ...buttonStyle, background: "#b91c1c" }}>
              Retry
            </button>
          </section>
        ) : null}

        {!isLoading && !error && summary ? (
          <>
            <section className="panel mode-banner">
              <div>
                <h2 className="section-title" style={{ marginBottom: 6 }}>Operating Mode</h2>
                <p className="section-subtitle" style={{ marginTop: 0 }}>
                  Simulation and Razorpay Test Mode are intentionally separated to prevent interpretation errors during demos.
                </p>
                {razorpayStatus ? (
                  <>
                    <p className="mode-meta">
                      Razorpay checks: Test Mode {razorpayStatus.test_mode ? "ON" : "OFF"} | Adapter {razorpayStatus.adapter_mode || "unknown"} | Webhook {razorpayStatus.webhook_configured ? "configured" : "missing"} | Live Mode {razorpayStatus.live_mode_detected ? "detected" : "not detected"} | API connectivity {razorpayStatus.api_connectivity ? "connected" : "not connected"}{razorpayStatus.api_connectivity_reason ? ` (${razorpayStatus.api_connectivity_reason})` : ""}
                    </p>
                    <p className="mode-meta">
                      Last successful Razorpay API operation: {razorpayStatus.last_successful_razorpay_operation
                        ? `${razorpayStatus.last_successful_razorpay_operation.operation} ${razorpayStatus.last_successful_razorpay_operation.payment_link_id} (${formatIsoTimestamp(razorpayStatus.last_successful_razorpay_operation.updated_at)})`
                        : "none"}
                    </p>
                    <p className="mode-meta">
                      Last webhook event: {razorpayStatus.last_event
                        ? `${razorpayStatus.last_event} (${razorpayStatus.last_event_status || "unknown"}) ${formatIsoTimestamp(razorpayStatus.last_event_received_at || null)}`
                        : "none"}
                    </p>
                  </>
                ) : (
                  <p className="mode-meta">Razorpay integration status not available.</p>
                )}
              </div>
              <span className="mode-badge" style={{ color: modeTone, background: modeBadgeBackground }}>
                {summary.mode_label.toUpperCase()}
              </span>
            </section>

            {isEmptySummary(summary) ? (
              <section className="panel empty-block">
                <h3 className="section-title">No command center metrics yet</h3>
                <p className="section-subtitle">
                  Metrics appear after failed-payment workflows create opportunities and attempt recovery actions.
                </p>
              </section>
            ) : (
              <section className="panel">
                <h2 className="section-title">Revenue Recovery Snapshot</h2>
                <p className="section-subtitle">Live KPI set for risk, execution, policy gates, and net impact.</p>
                <div className="kpi-grid" style={{ marginTop: 12 }}>
                  <MetricCard title="Revenue at Risk" value={formatMinorCurrency(summary.revenue_at_risk_minor)} context="Failed payments not yet recovered" />
                  <MetricCard title="Recovered Revenue" value={formatMinorCurrency(summary.gross_recovered_minor)} context={`Recovered ${formatPercent(Math.max(0, recoveredCoverage))} of recoverable revenue`} />
                  <MetricCard title="Recovery Rate" value={formatPercent(summary.recovery_rate)} context="Recovered / recoverable ratio" />
                  <MetricCard title="Active Opportunities" value={String(summary.active_opportunities)} context="Currently queued or in-progress" />
                  <MetricCard title="Recovery Attempts" value={String(summary.recovery_attempts)} context="Total attempts executed" />
                  <MetricCard title="Blocked / Escalated" value={`${summary.blocked_actions} / ${summary.escalated_actions ?? summary.escalations}`} context="Guardrails preventing unsafe execution" />
                  <MetricCard title="Net Recovered" value={formatMinorCurrency(summary.net_recovered_minor)} context="Recovered less intervention cost" />
                </div>
              </section>
            )}

            <section className="panel">
              <h3 className="section-title">Policy Outcomes</h3>
              <p className="section-subtitle">Deterministic policy decisions across current command center data.</p>
              <div className="pill-row" style={{ marginTop: 8 }}>
                <Badge tone="pass" text={`ALLOWED ${summary.allowed_actions ?? summary.approved_actions}`} />
                <Badge tone="fail" text={`BLOCKED ${summary.blocked_actions}`} />
                <Badge tone="pending" text={`ESCALATED ${summary.escalated_actions ?? summary.escalations}`} />
              </div>
            </section>

            <section className="workspace-grid">
              <article className="panel opportunities-panel">
                <h3 className="section-title">Opportunities</h3>
                <p className="section-subtitle">Prioritize by risk, expected recovery, confidence, and policy outcome.</p>
                <div className="filter-grid">
                  <div className="form-field form-field-full">
                    <label htmlFor="opportunity-search" className="field-label">Search opportunities</label>
                    <input
                      id="opportunity-search"
                      value={searchInput}
                      onChange={(event) => setSearchInput(event.target.value)}
                      placeholder="Search id, reason, action, customer"
                      className="field"
                    />
                  </div>
                  <div className="filter-row" style={{ gridTemplateColumns: isMobile ? "1fr" : "repeat(2, minmax(0, 1fr))" }}>
                    <div className="form-field">
                      <label htmlFor="opportunity-status" className="field-label">Status</label>
                      <select id="opportunity-status" value={statusFilter} onChange={(event) => { resetCursorPagination(); setStatusFilter(event.target.value); }} className="select">
                        <option value="ALL">All Status</option>
                        <option value="OPEN">OPEN</option>
                        <option value="RESOLVED">RESOLVED</option>
                        <option value="CLOSED">CLOSED</option>
                      </select>
                    </div>
                    <div className="form-field">
                      <label htmlFor="opportunity-action" className="field-label">Action</label>
                      <select id="opportunity-action" value={actionFilter} onChange={(event) => { resetCursorPagination(); setActionFilter(event.target.value); }} className="select">
                        <option value="ALL">All Actions</option>
                        <option value="RETRY">RETRY</option>
                        <option value="DELAYED_RETRY">DELAYED_RETRY</option>
                        <option value="RECOVERY_PROMPT">RECOVERY_PROMPT</option>
                        <option value="ALTERNATE_PAYMENT_PATH">ALTERNATE_PAYMENT_PATH</option>
                        <option value="ESCALATE">ESCALATE</option>
                      </select>
                    </div>
                    <div className="form-field">
                      <label htmlFor="opportunity-risk-bucket" className="field-label">Risk bucket</label>
                      <select id="opportunity-risk-bucket" value={riskBucketFilter} onChange={(event) => { resetCursorPagination(); setRiskBucketFilter(event.target.value); }} className="select">
                        <option value="ALL">All Risk Buckets</option>
                        <option value="LOW">LOW</option>
                        <option value="MEDIUM">MEDIUM</option>
                        <option value="HIGH">HIGH</option>
                      </select>
                    </div>
                    <div className="form-field">
                      <label htmlFor="opportunity-sort" className="field-label">Sort by</label>
                      <select
                        id="opportunity-sort"
                        value={sortBy}
                        onChange={(event) => {
                          const nextSort = event.target.value;
                          if (opportunityPaginationMode === "cursor" && nextSort !== "updated_desc") {
                            setCursorHelperMessage("Cursor mode supports Latest Updated sort only.");
                            return;
                          }
                          resetCursorPagination();
                          setSortBy(nextSort);
                        }}
                        className="select"
                      >
                        <option value="updated_desc">Latest Updated</option>
                        <option value="risk_desc">Risk Amount High-Low</option>
                        <option value="risk_asc">Risk Amount Low-High</option>
                        <option value="confidence_desc">Confidence High-Low</option>
                        <option value="probability_desc">Recovery Probability High-Low</option>
                      </select>
                    </div>
                    <div className="form-field">
                      <label htmlFor="opportunity-pagination-mode" className="field-label">Pagination mode</label>
                      <select
                        id="opportunity-pagination-mode"
                        value={opportunityPaginationMode}
                        onChange={(event) => {
                          const mode = event.target.value === "cursor" ? "cursor" : "page";
                          let cursorSortResetApplied = false;
                          if (mode === "cursor" && sortBy !== "updated_desc") {
                            setSortBy("updated_desc");
                            cursorSortResetApplied = true;
                          }
                          setOpportunityPaginationMode(mode);
                          resetCursorPagination();
                          if (cursorSortResetApplied) {
                            setCursorHelperMessage("Cursor mode supports Latest Updated sort only. Sort has been reset.");
                          }
                        }}
                        className="select"
                      >
                        <option value="page">Page Pagination</option>
                        <option value="cursor">Cursor Pagination</option>
                      </select>
                    </div>
                  </div>
                  {opportunityPaginationMode === "cursor" ? (
                    <p className="meta cursor-mode-hint">Cursor mode only supports Latest Updated.</p>
                  ) : null}
                  <div className="action-row filter-actions">
                    <button
                      onClick={() => {
                        resetCursorPagination();
                        setSearchFilter(searchInput);
                      }}
                      className="btn"
                      style={buttonStyle}
                    >
                      Apply Filters
                    </button>
                    <button
                      onClick={() => {
                        setSearchInput("");
                        setSearchFilter("");
                        setStatusFilter("ALL");
                        setActionFilter("ALL");
                        setRiskBucketFilter("ALL");
                        setSortBy("updated_desc");
                        setOpportunityPaginationMode("page");
                        resetCursorPagination();
                      }}
                      className="btn btn-secondary"
                      style={{ ...buttonStyle, background: "#475569" }}
                    >
                      Reset
                    </button>
                  </div>
                </div>

                {isOpportunityLoading ? <p className="meta opportunities-loading">Refreshing opportunities...</p> : null}

                {opportunities.length === 0 ? (
                  <div className="empty-block opportunities-empty">
                    <p className="meta" style={{ margin: 0 }}>
                      No opportunities match this filter set. Adjust filters or reset to inspect all active opportunities.
                    </p>
                  </div>
                ) : (
                  <div className={`table-wrap ${isTabletOrLower ? "table-wrap-mobile" : ""}`}>
                    <table className="table opportunities-table">
                      <thead>
                        <tr>
                          <th className="sticky-col">Opportunity</th>
                          <th>Risk</th>
                          <th>Amount</th>
                          <th>Expected Recovery</th>
                          <th>Confidence</th>
                          <th>Policy / Action</th>
                          <th>Status</th>
                          <th>Updated</th>
                        </tr>
                      </thead>
                      <tbody>
                        {opportunities.map((item) => {
                          const isSelected = item.id === selectedOpportunityId;
                          return (
                            <tr
                              key={item.id}
                              onClick={() => setSelectedOpportunityId(item.id)}
                              className={`row-selectable ${isSelected ? "row-selected" : ""}`}
                            >
                              <td className="sticky-col">
                                <strong>#{item.id}</strong>
                                <p className="meta" style={{ marginTop: 4 }}>{item.customer_reference || "-"}</p>
                                <p className="meta" style={{ marginTop: 4 }}>{item.failure_reason || item.failure_category || "-"}</p>
                              </td>
                              <td>
                                <Badge tone={toRiskTone(item.risk_bucket)} text={item.risk_bucket || "UNKNOWN"} />
                              </td>
                              <td>{formatMinorCurrency(item.amount_at_risk_minor)}</td>
                              <td>
                                {formatMinorCurrency(item.expected_recovery_minor)}
                                <p className="meta" style={{ marginTop: 4 }}>
                                  Net {formatMinorCurrency(item.expected_net_recovery_minor)}
                                </p>
                              </td>
                              <td>
                                <p style={{ margin: 0 }}>{formatPercentValue(item.confidence)}</p>
                                <p className="meta" style={{ marginTop: 4 }}>Recovery {formatPercentValue(item.recovery_probability)}</p>
                              </td>
                              <td>
                                <div className="pill-row">
                                  <Badge tone={toPolicyTone(item.policy_result)} text={item.policy_result || "PENDING"} />
                                </div>
                                <p className="meta" style={{ marginTop: 4 }}>{item.recommended_action || "NO_ACTION"}</p>
                              </td>
                              <td>
                                <Badge tone={toOutcomeTone(item.latest_verified_outcome || item.latest_attempt_status || item.status)} text={item.status} />
                              </td>
                              <td>
                                <span className="meta">{formatIsoTimestamp(item.updated_at)}</span>
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                )}

                {isTabletOrLower ? (
                  <p className="meta table-scroll-tip">
                    Tip: horizontally scroll the table to compare risk, confidence, and policy context while keeping the opportunity column pinned.
                  </p>
                ) : null}

                <div className="pagination-row">
                  <p className="meta">
                    {opportunityPaginationMode === "cursor"
                      ? `Cursor mode | Showing ${opportunities.length} of ${opportunityTotalCount}`
                      : `Page ${opportunityPage} / ${opportunityTotalPages} | Showing ${opportunities.length} of ${opportunityTotalCount}`}
                  </p>
                  <div className="action-row">
                    <div className="inline-field">
                      <label htmlFor="opportunity-page-size" className="field-label field-label-inline">Rows per page</label>
                      <select
                        id="opportunity-page-size"
                        value={String(opportunityPageSize)}
                        onChange={(event) => {
                          resetCursorPagination();
                          setOpportunityPageSize(parseNumber(event.target.value, 20));
                        }}
                        className="select"
                      >
                        <option value="10">10</option>
                        <option value="20">20</option>
                        <option value="40">40</option>
                        <option value="80">80</option>
                      </select>
                    </div>
                    <button
                      onClick={() => {
                        if (opportunityPaginationMode === "cursor") {
                          const previousCursor = opportunityCursorHistory[opportunityCursorHistory.length - 1] || null;
                          setOpportunityCursorHistory((prev) => prev.slice(0, Math.max(0, prev.length - 1)));
                          setOpportunityCursor(previousCursor);
                          return;
                        }
                        setOpportunityPage((prev) => Math.max(1, prev - 1));
                      }}
                      disabled={!opportunityHasPrev}
                      className="btn"
                      style={{ ...buttonStyle, opacity: opportunityHasPrev ? 1 : 0.5 }}
                    >
                      Prev
                    </button>
                    <button
                      onClick={() => {
                        if (opportunityPaginationMode === "cursor") {
                          if (!opportunityNextCursor) {
                            return;
                          }
                          setOpportunityCursorHistory((prev) => [...prev, opportunityCursor || ""]);
                          setOpportunityCursor(opportunityNextCursor);
                          return;
                        }
                        setOpportunityPage((prev) => prev + 1);
                      }}
                      disabled={!opportunityHasNext}
                      className="btn"
                      style={{ ...buttonStyle, opacity: opportunityHasNext ? 1 : 0.5 }}
                    >
                      Next
                    </button>
                  </div>
                </div>

                {opportunityPaginationMode === "cursor" ? (
                  <div className="action-row cursor-actions">
                    <button onClick={resetCursorPagination} className="btn" style={{ ...buttonStyle, padding: "6px 10px", fontSize: 12 }}>
                      Jump to Start
                    </button>
                    <button onClick={handleCopyCursorToken} className="btn" style={{ ...buttonStyle, padding: "6px 10px", fontSize: 12, background: "#1d4ed8" }}>
                      Copy Cursor
                    </button>
                    <button onClick={handleShareCursorLink} className="btn" style={{ ...buttonStyle, padding: "6px 10px", fontSize: 12, background: "#0f766e" }}>
                      Copy/Share Cursor Link
                    </button>
                    <span className="meta">Current: {opportunityCursor ? `${opportunityCursor.slice(0, 14)}...` : "START"}</span>
                  </div>
                ) : null}

                {cursorHelperMessage ? <p className="meta cursor-helper-message">{cursorHelperMessage}</p> : null}
              </article>

              <article className="panel detail-panel">
                <h3 className="section-title">Opportunity Detail & Explainability</h3>
                <p className="section-subtitle">From failed payment signal to verified recovered outcome.</p>
                {!selectedItem ? (
                  <div className="empty-block detail-empty">
                    <p className="meta" style={{ margin: 0 }}>Select an opportunity to inspect workflow evidence and policy traceability.</p>
                  </div>
                ) : null}
                {selectedItem && isDetailLoading ? <p className="meta detail-loading">Loading opportunity detail...</p> : null}
                {selectedItem && !isDetailLoading && detail ? (
                  <div className="detail-grid detail-content-grid">
                    <article className="detail-card">
                      <h4>Recovery Journey</h4>
                      <div className="stage-flow">
                        {[
                          "Payment Failed",
                          "Revenue Opportunity",
                          "AI Diagnosis",
                          "Policy Decision",
                          "Recovery Action",
                          "Payment",
                          "Verification",
                          "Recovered",
                        ].map((step) => {
                          const reached = detail.recovery_state.stages.some((stage) => stage.reached && stage.name.toLowerCase().includes(step.toLowerCase().split(" ")[0]));
                          const active = detail.recovery_state.current.toLowerCase().includes(step.toLowerCase().split(" ")[0]);
                          return (
                            <div key={step} className={`stage-node ${reached ? "reached" : ""} ${active ? "active" : ""}`}>
                              <p className="stage-label">{step}</p>
                              <p className="stage-value">{active ? "Current" : reached ? "Reached" : "Pending"}</p>
                            </div>
                          );
                        })}
                      </div>
                    </article>

                    <div className="explainability-grid">
                      <DetailBlock
                        title="AI Recommendation"
                        content={[
                          `Diagnosis: ${detail.evidence.diagnosis || "-"}`,
                          `Recommended action: ${detail.action_traceability.recommended_action || "-"}`,
                          `Confidence: ${formatPercentValue(detail.opportunity.confidence)}`,
                          `Recovery probability: ${formatPercentValue(detail.opportunity.recovery_probability)}`,
                          `Provider: ${detail.evidence.provider || "-"} | Model: ${detail.evidence.model || "-"}`,
                        ]}
                      />
                      <DetailBlock
                        title="Deterministic Policy Decision"
                        content={[
                          `Policy result: ${detail.policy_checks.result || "-"}`,
                          `Execution allowed: ${detail.action_traceability.allow_execution === null ? "-" : detail.action_traceability.allow_execution ? "YES" : "NO"}`,
                          `Reason codes (failed): ${formatReasonCodes(detail.policy_checks.reason_codes.failed || [])}`,
                          `Reason codes (passed): ${formatReasonCodes(detail.policy_checks.reason_codes.passed || [])}`,
                          `Policy version: ${detail.policy_checks.policy_version || "-"}`,
                        ]}
                      />
                      <DetailBlock
                        title="Actual Payment Outcome"
                        content={[
                          `Payment status: ${detail.payment?.status || "-"}`,
                          `Latest attempt status: ${detail.action_traceability.latest_attempt_status || "-"}`,
                          `Verified outcome: ${detail.action_traceability.latest_verified_outcome || "-"}`,
                          `Gross recovered: ${formatMinorCurrency(detail.economics.gross_recovered_minor)}`,
                          `Net recovered: ${formatMinorCurrency(detail.economics.net_recovered_minor)}`,
                        ]}
                      />
                    </div>

                    <DetailBlock
                      title="Payment & Failure Context"
                      content={[
                        `Payment id: ${detail.payment?.razorpay_payment_id || "-"}`,
                        `Order id: ${detail.payment?.razorpay_order_id || "-"}`,
                        `Amount: ${detail.payment ? formatMinorCurrency(detail.payment.amount_minor) : "-"}`,
                        `Failure category: ${detail.failure.category || "-"}`,
                        `Failure reason: ${detail.failure.reason || "-"}`,
                        `Failure code: ${detail.failure.payment_failure_code || "-"}`,
                      ]}
                    />
                    <DetailBlock
                      title="Economic Impact"
                      content={[
                        `Expected recovery: ${formatMinorCurrency(detail.economics.expected_recovery_minor)}`,
                        `Intervention cost estimate: ${formatMinorCurrency(detail.economics.estimated_intervention_cost_minor)}`,
                        `Expected net recovery: ${formatMinorCurrency(detail.economics.expected_net_recovery_minor)}`,
                        `Total intervention cost: ${formatMinorCurrency(detail.economics.total_intervention_cost_minor)}`,
                      ]}
                    />
                    <article className="detail-card">
                      <h4>Evidence</h4>
                      <p>Decision source: {detail.evidence.decision_source || "-"}</p>
                      <p>Schema version: {detail.evidence.schema_version || "-"}</p>
                      <details className="evidence-details">
                        <summary>View model evidence JSON</summary>
                        <pre className="evidence-json">{serializeEvidence(detail.evidence.model_evidence || {})}</pre>
                      </details>
                    </article>
                    <TimelineGroups
                      groups={detail.timeline_groups}
                      collapsed={selectedTimelineCollapseState}
                      onCollapsedChange={updateSelectedTimelineCollapseState}
                    />
                    <DetailBlock
                      title="Audit Trail"
                      content={detail.audit_trail.length > 0
                        ? detail.audit_trail.map((item) => `${formatIsoTimestamp(item.timestamp)} ${item.event_type} (${item.outcome_status.toUpperCase()})`)
                        : ["No audit events yet."]}
                    />
                  </div>
                ) : null}
              </article>
            </section>

            <section className="panel">
              <h3 className="section-title">Evaluation Center</h3>
              <p className="section-subtitle">
                Held-out evaluation console comparing Baseline vs RecoverIQ on precision, recall, F1, false-positive cost, and recovered revenue.
              </p>

              <div className="filter-row evaluation-controls" style={{ marginTop: 10, gridTemplateColumns: isMobile ? "1fr" : "2fr 1fr 1fr 1fr auto" }}>
                <div className="form-field">
                  <label htmlFor="eval-dataset-version" className="field-label">Dataset version</label>
                  <input id="eval-dataset-version" value={runDatasetVersion} onChange={(e) => setRunDatasetVersion(e.target.value)} placeholder="phase11_dataset" className="field" />
                </div>
                <div className="form-field">
                  <label htmlFor="eval-split" className="field-label">Split</label>
                  <select id="eval-split" value={runSplit} onChange={(e) => setRunSplit(e.target.value)} className="select">
                    <option value="TEST">TEST</option>
                    <option value="VALIDATION">VALIDATION</option>
                    <option value="DEVELOPMENT">DEVELOPMENT</option>
                  </select>
                </div>
                <div className="form-field">
                  <label htmlFor="eval-seed" className="field-label">Generation seed</label>
                  <input id="eval-seed" value={runGenerationSeed} onChange={(e) => setRunGenerationSeed(e.target.value)} placeholder="42" className="field" />
                </div>
                <div className="form-field">
                  <label htmlFor="eval-total-cases" className="field-label">Total cases</label>
                  <input id="eval-total-cases" value={runTotalCases} onChange={(e) => setRunTotalCases(e.target.value)} placeholder="1000" className="field" />
                </div>
                <button onClick={runEvaluation} disabled={isRunSubmitting} className="btn" style={{ ...buttonStyle, opacity: isRunSubmitting ? 0.7 : 1 }}>
                  {isRunSubmitting ? "Running..." : "Run Evaluation"}
                </button>
              </div>

              <div className="eval-grid">
                <div className="detail-card run-history-card">
                  <h4>Run History</h4>
                  {evaluationHistory.length === 0 ? (
                    <div className="empty-block"><p className="meta" style={{ margin: 0 }}>No evaluation runs yet.</p></div>
                  ) : (
                    <div className="history-list">
                      {evaluationHistory.map((item) => (
                        <button
                          key={item.evaluation_run_id}
                          onClick={() => setSelectedEvaluationRunId(item.evaluation_run_id)}
                          className={`history-item ${item.evaluation_run_id === selectedEvaluationRunId ? "active" : ""}`}
                        >
                          <p style={{ margin: 0, fontWeight: 700, fontSize: 12 }}>{item.evaluation_run_id}</p>
                          <p className="meta" style={{ marginTop: 4 }}>Records {item.records} | F1 {formatPercent(item.f1)}</p>
                          <p className="meta" style={{ marginTop: 2 }}>{formatIsoTimestamp(item.last_created_at || null)}</p>
                        </button>
                      ))}
                    </div>
                  )}
                </div>

                <div className="detail-card">
                  <h4>Baseline vs RecoverIQ</h4>
                  {isEvaluationLoading ? <p className="meta">Loading run insights...</p> : null}
                  {!isEvaluationLoading && !selectedEvaluationRunId ? <p className="meta">Select an evaluation run to inspect results.</p> : null}
                  {!isEvaluationLoading && evaluationComparison ? (
                    <div className="detail-grid">
                      <table className="table">
                        <thead>
                          <tr>
                            <th>Metric</th>
                            <th>Baseline</th>
                            <th>RecoverIQ</th>
                            <th>Delta</th>
                          </tr>
                        </thead>
                        <tbody>
                          <tr>
                            <td>Precision</td>
                            <td>{formatPercent(evaluationComparison.baseline.precision)}</td>
                            <td>{formatPercent(evaluationComparison.recoveriq.precision)}</td>
                            <td className={toDeltaClass(evaluationComparison.deltas.precision_delta)}>{toDeltaLabel(evaluationComparison.deltas.precision_delta * 100)}</td>
                          </tr>
                          <tr>
                            <td>Recall</td>
                            <td>{formatPercent(evaluationComparison.baseline.recall)}</td>
                            <td>{formatPercent(evaluationComparison.recoveriq.recall)}</td>
                            <td className={toDeltaClass(evaluationComparison.deltas.recall_delta)}>{toDeltaLabel(evaluationComparison.deltas.recall_delta * 100)}</td>
                          </tr>
                          <tr>
                            <td>F1</td>
                            <td>{formatPercent(evaluationComparison.baseline.f1)}</td>
                            <td>{formatPercent(evaluationComparison.recoveriq.f1)}</td>
                            <td className={toDeltaClass(evaluationComparison.deltas.f1_delta)}>{toDeltaLabel(evaluationComparison.deltas.f1_delta * 100)}</td>
                          </tr>
                          <tr>
                            <td>Recovery rate</td>
                            <td>{formatPercent(evaluationComparison.baseline.recovery_rate)}</td>
                            <td>{formatPercent(evaluationComparison.recoveriq.recovery_rate)}</td>
                            <td className={toDeltaClass(evaluationComparison.deltas.recovery_rate_delta)}>{toDeltaLabel(evaluationComparison.deltas.recovery_rate_delta * 100)}</td>
                          </tr>
                          <tr>
                            <td>Revenue recovered</td>
                            <td>{formatMinorCurrency(evaluationComparison.baseline.gross_recovered_minor)}</td>
                            <td>{formatMinorCurrency(evaluationComparison.recoveriq.gross_recovered_minor)}</td>
                            <td className={toDeltaClass(evaluationComparison.deltas.net_recovered_minor_delta)}>{formatMinorCurrency(evaluationComparison.deltas.net_recovered_minor_delta)}</td>
                          </tr>
                          <tr>
                            <td>False-positive cost</td>
                            <td>{formatMinorCurrency(evaluationComparison.baseline.false_positive_exposure_minor)}</td>
                            <td>{formatMinorCurrency(evaluationComparison.recoveriq.false_positive_exposure_minor)}</td>
                            <td className={toDeltaClass(-evaluationComparison.deltas.false_positive_exposure_minor_delta)}>{formatMinorCurrency(evaluationComparison.deltas.false_positive_exposure_minor_delta)}</td>
                          </tr>
                        </tbody>
                      </table>

                      {evaluationDrilldown ? (
                        <DetailBlock
                          title="Drilldown"
                          content={[
                            `Confusion matrix TP/FP/FN/TN: ${evaluationDrilldown.confusion_matrix.tp}/${evaluationDrilldown.confusion_matrix.fp}/${evaluationDrilldown.confusion_matrix.fn}/${evaluationDrilldown.confusion_matrix.tn}`,
                            `False positives: ${evaluationDrilldown.false_positive_cost.count}`,
                            `False-positive exposure: ${formatMinorCurrency(evaluationDrilldown.false_positive_cost.financial_exposure_minor)}`,
                            `False-positive intervention cost: ${formatMinorCurrency(evaluationDrilldown.false_positive_cost.intervention_cost_minor)}`,
                            `Operational allowed/blocked/escalated/failed: ${evaluationDrilldown.operational.allowed}/${evaluationDrilldown.operational.blocked}/${evaluationDrilldown.operational.escalated}/${evaluationDrilldown.operational.failed}`,
                          ]}
                        />
                      ) : null}

                      <DetailBlock
                        title="Attribution Deltas"
                        content={[
                          ...Object.entries(evaluationComparison.attribution.action_level_deltas).map(
                            ([action, delta]) => `Action ${action}: ${delta >= 0 ? "+" : ""}${delta}`,
                          ),
                          ...Object.entries(evaluationComparison.attribution.policy_reason_deltas).map(
                            ([reason, delta]) => `Policy ${reason}: ${delta >= 0 ? "+" : ""}${delta}`,
                          ),
                        ]}
                      />
                    </div>
                  ) : null}
                </div>
              </div>
            </section>

            <section className="panel">
              <h3 className="section-title">Failure & Security Validation</h3>
              <p className="section-subtitle">Controlled failure scenarios with explicit expected vs actual behavior.</p>
              {failureScenarios.length === 0 ? (
                <div className="empty-block" style={{ marginTop: 10 }}><p className="meta" style={{ margin: 0 }}>No failure scenarios loaded.</p></div>
              ) : (
                <div className="security-grid" style={{ marginTop: 10 }}>
                  {failureScenarios.map((scenario) => (
                    <article key={scenario.scenario_id} className="readiness-check">
                      <div style={{ display: "flex", justifyContent: "space-between", gap: 10, alignItems: "start", flexWrap: "wrap" }}>
                        <div>
                          <h4 style={{ margin: 0, fontSize: 14 }}>{scenario.title}</h4>
                          <p className="meta" style={{ marginTop: 4 }}>Scenario: {scenario.description}</p>
                          <p className="meta" style={{ marginTop: 4 }}>Action: Trigger controlled failure path ({scenario.scenario_id})</p>
                          <p className="meta" style={{ marginTop: 4 }}>Expected result: {scenario.expected_behavior || `Error code ${scenario.expected_error_code}`}</p>
                          <p className="meta" style={{ marginTop: 4 }}>Actual result: {scenario.actual_behavior || "Available after trigger"}</p>
                          <p className="meta" style={{ marginTop: 4 }}>
                            Security implication: {scenario.severity.toUpperCase()} severity path must fail safely without bypassing policy controls.
                          </p>
                        </div>
                        <button onClick={() => triggerFailureScenario(scenario.scenario_id)} className="btn" style={buttonStyle}>
                          Trigger
                        </button>
                      </div>
                    </article>
                  ))}
                </div>
              )}
              {failureScenarioResult ? <p className="meta" style={{ marginTop: 12 }}>{failureScenarioResult}</p> : null}
            </section>

            <section className="panel">
              <h3 className="section-title">Readiness Validation</h3>
              <p className="section-subtitle">Execute acceptance workflow and capture PASS / PARTIAL / FAIL with evidence.</p>
              <button onClick={executeReadinessValidation} disabled={isReadinessRunning} className="btn" style={{ ...buttonStyle, marginTop: 8, opacity: isReadinessRunning ? 0.7 : 1 }}>
                {isReadinessRunning ? "Running workflow..." : "Run Readiness Workflow"}
              </button>

              {readinessValidation ? (
                <div className="detail-grid" style={{ marginTop: 12 }}>
                  <div className="pill-row">
                    <Badge tone={readinessValidation.status === "PASS" ? "pass" : readinessValidation.status === "FAIL" ? "fail" : "pending"} text={readinessValidation.status} />
                    <span className="meta">Pass {readinessValidation.summary.pass_count} | Partial {readinessValidation.summary.partial_count} | Fail {readinessValidation.summary.fail_count}</span>
                  </div>
                  {readinessValidation.checks.map((check) => (
                    <article key={check.id} className="readiness-check">
                      <div className="pill-row" style={{ marginBottom: 6 }}>
                        <Badge tone={check.status === "PASS" ? "pass" : check.status === "FAIL" ? "fail" : "pending"} text={check.status} />
                        <strong style={{ fontSize: 13 }}>{check.id}</strong>
                      </div>
                      <p style={{ margin: "0 0 4px", color: "#334155", fontSize: 13 }}>{check.message}</p>
                      <p className="meta" style={{ margin: 0 }}>Evidence: {serializeEvidence(check.evidence)}</p>
                    </article>
                  ))}
                </div>
              ) : null}
            </section>
          </>
        ) : null}
      </section>
    </main>
  );
}

function TimelineGroups({ groups, collapsed, onCollapsedChange }: {
  groups: OpportunityDetail["timeline_groups"];
  collapsed: Record<string, boolean>;
  onCollapsedChange: (nextState: Record<string, boolean>) => void;
}) {
  if (groups.length === 0) {
    return <DetailBlock title="Timeline" content={["No workflow timeline events available yet."]} />;
  }

  const totalPass = groups.reduce((sum, group) => sum + group.counts.pass, 0);
  const totalFail = groups.reduce((sum, group) => sum + group.counts.fail, 0);
  const totalPending = groups.reduce((sum, group) => sum + group.counts.pending, 0);

  return (
    <article className="detail-card">
      <h4>Timeline & Workflow Events</h4>
      <div className="pill-row" style={{ marginBottom: 8 }}>
        <Badge tone="pass" text={`PASS ${totalPass}`} />
        <Badge tone="fail" text={`FAIL ${totalFail}`} />
        <Badge tone="pending" text={`PENDING ${totalPending}`} />
        <button
          onClick={() => {
            const expanded: Record<string, boolean> = {};
            groups.forEach((group) => {
              expanded[group.group] = false;
            });
            onCollapsedChange(expanded);
          }}
          className="btn"
          style={{ ...buttonStyle, marginLeft: "auto", padding: "4px 8px", fontSize: 11 }}
        >
          Expand All
        </button>
        <button
          onClick={() => {
            const allCollapsed: Record<string, boolean> = {};
            groups.forEach((group) => {
              allCollapsed[group.group] = true;
            });
            onCollapsedChange(allCollapsed);
          }}
          className="btn"
          style={{ ...buttonStyle, padding: "4px 8px", fontSize: 11, background: "#475569" }}
        >
          Collapse All
        </button>
      </div>
      <div className="detail-grid">
        {groups.map((group) => (
          <section key={group.group} className="readiness-check timeline-group">
            <div className="timeline-group-header">
              <strong style={{ fontSize: 13 }}>{group.group}</strong>
              <Badge tone="pass" text={`PASS ${group.counts.pass}`} />
              <Badge tone="fail" text={`FAIL ${group.counts.fail}`} />
              <Badge tone="pending" text={`PENDING ${group.counts.pending}`} />
              <button
                onClick={() => onCollapsedChange({ ...collapsed, [group.group]: !collapsed[group.group] })}
                className="btn"
                style={{ ...buttonStyle, marginLeft: "auto", padding: "4px 8px", fontSize: 11 }}
              >
                {collapsed[group.group] ? "Expand" : "Collapse"}
              </button>
            </div>
            {!collapsed[group.group] ? (
              <div className="timeline-event-list">
                {group.events.map((event, index) => (
                  <div key={`${group.group}-${index}`} className="timeline-event-row">
                    <Badge tone={event.outcome_status} text={event.outcome_status.toUpperCase()} />
                    <div className="timeline-event-copy">
                      <p className="timeline-event-title">{event.event_type}</p>
                      <p className="meta">{formatIsoTimestamp(event.timestamp)}</p>
                      {event.reason ? <p className="meta">Reason: {event.reason}</p> : null}
                    </div>
                  </div>
                ))}
              </div>
            ) : null}
          </section>
        ))}
      </div>
    </article>
  );
}

function Badge({ tone, text }: { tone: "pass" | "fail" | "pending" | "neutral" | "high" | "medium" | "low"; text: string }) {
  const styleMap: Record<string, CSSProperties> = {
    pass: { background: "#dcfce7", color: "#166534" },
    fail: { background: "#fee2e2", color: "#991b1b" },
    pending: { background: "#fef3c7", color: "#92400e" },
    neutral: { background: "#e2e8f0", color: "#334155" },
    high: { background: "#fee2e2", color: "#9f1239" },
    medium: { background: "#ffedd5", color: "#9a3412" },
    low: { background: "#dcfce7", color: "#166534" },
  };

  return (
    <span
      style={{
        ...(styleMap[tone] || styleMap.pending),
        borderRadius: 999,
        padding: "2px 8px",
        fontSize: 11,
        fontWeight: 700,
        display: "inline-block",
      }}
    >
      {text}
    </span>
  );
}

function MetricCard({ title, value, context }: { title: string; value: string; context: string }) {
  return (
    <article className="kpi-card">
      <p className="kpi-label">{title}</p>
      <p className="kpi-value">{value}</p>
      <p className="kpi-context">{context}</p>
    </article>
  );
}

function DetailBlock({ title, content }: { title: string; content: string[] }) {
  return (
    <article className="detail-card">
      <h4>{title}</h4>
      {content.map((line, index) => (
        <p key={`${title}-${index}`}>
          {line}
        </p>
      ))}
    </article>
  );
}
