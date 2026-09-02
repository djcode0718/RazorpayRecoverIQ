import { useEffect, useState, useMemo, useCallback } from "react";
import "./app.css";

// Types
import {
  Summary,
  TrendDataPoint,
  DashboardEvent,
  OpportunityListItem,
  OpportunityDetail,
  EvaluationSummary,
  EvaluationComparisonResponse,
  EvaluationDrilldownResponse,
  FailureScenario,
  ReadinessValidationData,
  OperatingStatus,
  HealthItem,
} from "./types";

// API
import { api } from "./services/api";

// Common Components
import { TableSkeleton, KpiGridSkeleton } from "./components/common/Skeletons";
import { EmptyState } from "./components/common/EmptyState";
import { ErrorBanner } from "./components/common/ErrorBanner";
import { RecoverySuccessModal } from "./components/common/RecoverySuccessModal";
import { GuidedDemoModal } from "./components/common/GuidedDemoModal";

// Layout Components
import { Header } from "./components/layout/Header";
import { Navigation } from "./components/layout/Navigation";

// Command Center Components
import { ExecutiveStoryBanner } from "./components/commandCenter/ExecutiveStoryBanner";
import { ExecutiveKpiGrid } from "./components/commandCenter/ExecutiveKpiGrid";
import { ActionCenter } from "./components/commandCenter/ActionCenter";
import { ActionableInsights } from "./components/commandCenter/ActionableInsights";
import { RecoveryImpactChart } from "./components/commandCenter/RecoveryImpactChart";
import { RecoveryFunnel } from "./components/commandCenter/RecoveryFunnel";
import { CopilotCard } from "./components/commandCenter/CopilotCard";
import { PriorityQueue } from "./components/commandCenter/PriorityQueue";
import { EventStream } from "./components/commandCenter/EventStream";
import { TrendChart } from "./components/commandCenter/TrendChart";
import { OperatingHealth } from "./components/commandCenter/OperatingHealth";

// Opportunities Components
import { OpportunityFilters } from "./components/opportunities/OpportunityFilters";
import { OpportunityTable } from "./components/opportunities/OpportunityTable";
import { OpportunityDrawer } from "./components/opportunities/OpportunityDrawer";

// Evaluation Components
import { EvaluationHero } from "./components/evaluation/EvaluationHero";
import { ExecutiveMetricsCards } from "./components/evaluation/ExecutiveMetricsCards";
import { ComparisonMatrix } from "./components/evaluation/ComparisonMatrix";
import { ConfusionMatrix } from "./components/evaluation/ConfusionMatrix";
import { SampleTestCasesTable } from "./components/evaluation/SampleTestCasesTable";
import { ReproducibilityCard } from "./components/evaluation/ReproducibilityCard";
import { EvaluationRunForm } from "./components/evaluation/EvaluationRunForm";

// Reliability Components
import { ReliabilityHero } from "./components/reliability/ReliabilityHero";
import { OperatingHealthCards } from "./components/reliability/OperatingHealthCards";
import { FailureScenariosSection } from "./components/reliability/FailureScenariosSection";
import { SecurityControlsMatrix } from "./components/reliability/SecurityControlsMatrix";
import { TechnicalIntegrationDetails } from "./components/reliability/TechnicalIntegrationDetails";

// Readiness Components
import { ReadinessHero } from "./components/readiness/ReadinessHero";
import { RemediationBanner } from "./components/readiness/RemediationBanner";
import { ReadinessCheckGrid } from "./components/readiness/ReadinessCheckGrid";

export function App() {
  // Navigation
  const [activeTab, setActiveTab] = useState<string>("Command Center");

  // Modals & Overlays
  const [isDemoTourOpen, setIsDemoTourOpen] = useState<boolean>(false);
  const [successModalData, setSuccessModalData] = useState<{
    isOpen: boolean;
    opportunity: OpportunityListItem | null;
    detail: OpportunityDetail | null;
  }>({
    isOpen: false,
    opportunity: null,
    detail: null,
  });

  // Telemetry & Metrics
  const [summary, setSummary] = useState<Summary | null>(null);
  const [dashboardTrend, setDashboardTrend] = useState<TrendDataPoint[]>([]);
  const [dashboardEvents, setDashboardEvents] = useState<DashboardEvent[]>([]);
  const [razorpayStatus, setRazorpayStatus] = useState<any | null>(null);

  // Opportunities
  const [opportunities, setOpportunities] = useState<OpportunityListItem[]>([]);
  const [selectedOpportunityId, setSelectedOpportunityId] = useState<number | null>(null);
  const [detail, setDetail] = useState<OpportunityDetail | null>(null);
  const [opportunityPage, setOpportunityPage] = useState<number>(1);
  const [opportunityPageSize, setOpportunityPageSize] = useState<number>(20);
  const [opportunityTotalCount, setOpportunityTotalCount] = useState<number>(0);
  const [opportunityTotalPages, setOpportunityTotalPages] = useState<number>(1);
  const [opportunityHasNext, setOpportunityHasNext] = useState<boolean>(false);
  const [opportunityHasPrev, setOpportunityHasPrev] = useState<boolean>(false);
  const [statusFilter, setStatusFilter] = useState<string>("ALL");
  const [actionFilter, setActionFilter] = useState<string>("ALL");
  const [searchFilter, setSearchFilter] = useState<string>("");
  const [confidenceFilter, setConfidenceFilter] = useState<string>("ALL");
  const [amountFilter, setAmountFilter] = useState<string>("ALL");

  // Evaluation
  const [evaluationHistory, setEvaluationHistory] = useState<EvaluationSummary[]>([]);
  const [selectedEvaluationRunId, setSelectedEvaluationRunId] = useState<string | null>(null);
  const [evaluationComparison, setEvaluationComparison] = useState<EvaluationComparisonResponse["data"] | null>(null);
  const [evaluationDrilldown, setEvaluationDrilldown] = useState<EvaluationDrilldownResponse["data"] | null>(null);
  const [isEvaluationLoading, setIsEvaluationLoading] = useState<boolean>(false);
  const [isRunSubmitting, setIsRunSubmitting] = useState<boolean>(false);

  // Reliability & Security
  const [failureScenarios, setFailureScenarios] = useState<FailureScenario[]>([]);
  const [expandedScenarioId, setExpandedScenarioId] = useState<string | null>(null);
  const [activeResilienceScenario, setActiveResilienceScenario] = useState<any | null>(null);
  const [resilienceError, setResilienceError] = useState<string | null>(null);
  const [failureScenarioResult, setFailureScenarioResult] = useState<string>("");
  const [isTriggeringScenario, setIsTriggeringScenario] = useState<boolean>(false);

  // Production Readiness
  const [readinessValidation, setReadinessValidation] = useState<ReadinessValidationData | null>(null);
  const [isReadinessRunning, setIsReadinessRunning] = useState<boolean>(false);

  // UI & Loading States
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [isOpportunityLoading, setIsOpportunityLoading] = useState<boolean>(false);
  const [isDetailLoading, setIsDetailLoading] = useState<boolean>(false);
  const [isExecutingRecovery, setIsExecutingRecovery] = useState<boolean>(false);
  const [executionMessage, setExecutionMessage] = useState<string | null>(null);
  const [isDemoMutating, setIsDemoMutating] = useState<boolean>(false);
  const [demoMutationMessage, setDemoMutationMessage] = useState<string>("");
  const [autoRefreshEnabled, setAutoRefreshEnabled] = useState<boolean>(false);

  // Error States
  const [primaryError, setPrimaryError] = useState<string | null>(null);
  const [trendError, setTrendError] = useState<string | null>(null);
  const [eventsError, setEventsError] = useState<string | null>(null);
  const [opportunitiesError, setOpportunitiesError] = useState<string | null>(null);
  const [evaluationError, setEvaluationError] = useState<string | null>(null);

  // Operating status derived object
  const operatingStatus: OperatingStatus = useMemo(() => {
    return summary?.operating_status || razorpayStatus?.operating_status || {
      data_source: "SEEDED DEMO",
      payment_environment: razorpayStatus?.test_mode ? "RAZORPAY TEST" : "SIMULATION",
      ai_provider: "MOCK/FALLBACK",
      ai_provider_note: "Deterministic mock provider active",
      policy_engine: "ACTIVE",
      policy_engine_note: "Safety policy rules & threshold evaluation active",
      webhook: razorpayStatus?.webhook_configured ? (razorpayStatus?.last_event ? "VERIFIED" : "WAITING") : "DEGRADED",
      webhook_note: razorpayStatus?.webhook_configured ? "Webhook active" : "Webhook not configured",
      api_connectivity: razorpayStatus?.api_connectivity,
      api_connectivity_reason: razorpayStatus?.api_connectivity_reason,
      last_event: razorpayStatus?.last_event,
      last_event_received_at: razorpayStatus?.last_event_received_at,
    };
  }, [summary?.operating_status, razorpayStatus]);

  // Operating health item matrix
  const healthItems: HealthItem[] = useMemo(() => {
    const isWebhookHealthy =
      operatingStatus.webhook === "VERIFIED" ||
      operatingStatus.webhook === "CONFIGURED" ||
      operatingStatus.webhook === "WAITING";

    const isAiHealthy = operatingStatus.ai_provider !== "UNAVAILABLE";
    const isPolicyHealthy = operatingStatus.policy_engine === "ACTIVE";

    return [
      {
        label: "Razorpay Gateway",
        healthy: Boolean(operatingStatus.api_connectivity),
        statusText: operatingStatus.api_connectivity
          ? "CONNECTED"
          : operatingStatus.payment_environment === "RAZORPAY TEST"
          ? "DISCONNECTED"
          : "SIMULATION",
        note:
          operatingStatus.api_connectivity_reason ||
          (operatingStatus.api_connectivity ? "Connected (Test Mode)" : "Simulation / Local Mode"),
      },
      {
        label: "Webhook Gateway",
        healthy: isWebhookHealthy,
        statusText: operatingStatus.webhook,
        note:
          operatingStatus.webhook_note ||
          (operatingStatus.last_event ? `Last event: ${operatingStatus.last_event}` : "Waiting for events"),
      },
      {
        label: "AI Intelligence",
        healthy: isAiHealthy,
        statusText: operatingStatus.ai_provider,
        note: operatingStatus.ai_provider_note || "Autonomous machine learning classification active",
      },
      {
        label: "Policy Engine",
        healthy: isPolicyHealthy,
        statusText: operatingStatus.policy_engine,
        note: operatingStatus.policy_engine_note || "Deterministic 7/7 safety controls enforced",
      },
    ];
  }, [operatingStatus]);

  // Load Opportunities
  const loadOpportunities = useCallback(
    async (showLoader = false) => {
      if (showLoader) {
        setIsOpportunityLoading(true);
      }
      setOpportunitiesError(null);
      try {
        const data = await api.getOpportunities({
          page: opportunityPage,
          pageSize: opportunityPageSize,
          status: statusFilter,
          action: actionFilter,
          search: searchFilter,
        });

        setOpportunities(data.items);
        setOpportunityTotalCount(data.total_count);
        setOpportunityTotalPages(data.total_pages);
        setOpportunityHasNext(data.has_next);
        setOpportunityHasPrev(data.has_prev);

        if (data.items.length === 0) {
          setSelectedOpportunityId(null);
          setDetail(null);
        } else if (selectedOpportunityId) {
          const hasSelected = data.items.some((item) => item.id === selectedOpportunityId);
          if (!hasSelected) {
            setSelectedOpportunityId(null);
          }
        }
      } catch (err: any) {
        setOpportunitiesError(err.message || "Unable to load opportunities.");
      } finally {
        if (showLoader) {
          setIsOpportunityLoading(false);
        }
      }
    },
    [opportunityPage, opportunityPageSize, statusFilter, actionFilter, searchFilter, selectedOpportunityId]
  );

  // Load Opportunity Detail
  const loadOpportunityDetail = useCallback(async (id: number) => {
    setIsDetailLoading(true);
    try {
      const data = await api.getOpportunityDetail(id);
      setDetail(data);
    } catch (err: any) {
      setExecutionMessage(err.message || `Unable to load details for opportunity #${id}`);
    } finally {
      setIsDetailLoading(false);
    }
  }, []);

  // Load Evaluation Insights for a specific run ID
  const loadEvaluationInsights = useCallback(async (runId: string) => {
    setIsEvaluationLoading(true);
    setEvaluationError(null);
    try {
      const data = await api.getEvaluationInsights(runId);
      setEvaluationComparison(data.comparison);
      setEvaluationDrilldown(data.drilldown);
    } catch (err: any) {
      setEvaluationError(err.message || "Unable to load evaluation benchmark data.");
    } finally {
      setIsEvaluationLoading(false);
    }
  }, []);

  // Load Evaluation Run History
  const loadEvaluationHistory = useCallback(async () => {
    try {
      const items = await api.getEvaluationHistory(10);
      setEvaluationHistory(items);
      if (items.length > 0 && !selectedEvaluationRunId) {
        const firstRunId = items[0].evaluation_run_id;
        setSelectedEvaluationRunId(firstRunId);
        loadEvaluationInsights(firstRunId);
      }
    } catch (err: any) {
      setEvaluationError(err.message || "Unable to load evaluation history.");
    }
  }, [selectedEvaluationRunId, loadEvaluationInsights]);

  // Load Full Command Center Data
  const loadCommandCenter = useCallback(async () => {
    setIsLoading(true);
    setPrimaryError(null);
    setTrendError(null);
    setEventsError(null);

    const promises = [
      api
        .getSummary()
        .then((data) => setSummary(data))
        .catch((err) => {
          setPrimaryError(err.message);
        }),
      api
        .getTrend()
        .then((data) => setDashboardTrend(data))
        .catch((err) => setTrendError(err.message)),
      api
        .getEvents()
        .then((data) => setDashboardEvents(data))
        .catch((err) => setEventsError(err.message)),
      api
        .getRazorpayStatus()
        .then((data) => setRazorpayStatus(data))
        .catch(() => undefined),
      api
        .getFailureScenarios()
        .then((data) => setFailureScenarios(data))
        .catch(() => undefined),
      loadOpportunities(false),
      loadEvaluationHistory(),
    ];

    await Promise.all(promises);
    setIsLoading(false);
  }, [loadOpportunities, loadEvaluationHistory]);

  // Initial Load
  useEffect(() => {
    loadCommandCenter();
  }, []);

  // Sync opportunity list on filter/page changes
  useEffect(() => {
    loadOpportunities(true);
  }, [statusFilter, actionFilter, searchFilter, opportunityPage, opportunityPageSize]);

  // Sync drawer when selected opportunity ID changes
  useEffect(() => {
    if (selectedOpportunityId !== null) {
      loadOpportunityDetail(selectedOpportunityId);
      document.body.classList.add("drawer-open");
    } else {
      setDetail(null);
      setExecutionMessage(null);
      document.body.classList.remove("drawer-open");
    }
    return () => {
      document.body.classList.remove("drawer-open");
    };
  }, [selectedOpportunityId, loadOpportunityDetail]);

  // Escape key handler for drawer & modals
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        if (successModalData.isOpen) {
          setSuccessModalData({ isOpen: false, opportunity: null, detail: null });
        } else if (isDemoTourOpen) {
          setIsDemoTourOpen(false);
        } else if (selectedOpportunityId !== null) {
          setSelectedOpportunityId(null);
        }
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [selectedOpportunityId, successModalData.isOpen, isDemoTourOpen]);

  // Auto-refresh interval (15s)
  useEffect(() => {
    if (!autoRefreshEnabled) return;
    const intervalId = window.setInterval(() => {
      loadCommandCenter();
      if (selectedOpportunityId) {
        loadOpportunityDetail(selectedOpportunityId);
      }
    }, 15000);
    return () => window.clearInterval(intervalId);
  }, [autoRefreshEnabled, selectedOpportunityId, loadCommandCenter, loadOpportunityDetail]);

  // Handlers
  const handleTabChange = (newTab: string) => {
    setActiveTab(newTab);
    setSelectedOpportunityId(null);
  };

  const handleNavigateFromKpi = (tab: string, filter?: Record<string, string>) => {
    setActiveTab(tab);
    if (filter) {
      if (filter.status) setStatusFilter(filter.status);
      if (filter.action) setActionFilter(filter.action);
    }
  };

  const handleExecuteRecovery = async (id: number) => {
    setIsExecutingRecovery(true);
    setExecutionMessage(null);
    try {
      await api.executeRecovery(id);
      setExecutionMessage("✓ Recovery action triggered successfully. Webhook verified.");
      await loadOpportunities(false);
      await loadOpportunityDetail(id);
      const updatedSummary = await api.getSummary();
      setSummary(updatedSummary);

      const opp = opportunities.find((o) => o.id === id) || null;
      if (opp && detail) {
        setSuccessModalData({
          isOpen: true,
          opportunity: { ...opp, status: "RESOLVED", outcome: "RECOVERED" },
          detail,
        });
      }
    } catch (err: any) {
      setExecutionMessage(err.message || "Execution failed.");
    } finally {
      setIsExecutingRecovery(false);
    }
  };

  const handleRunEvaluation = async (params: {
    dataset_version: string;
    split: string;
    generation_seed: number;
    total_cases: number;
  }) => {
    setIsRunSubmitting(true);
    try {
      const result = await api.runEvaluation(params);
      setSelectedEvaluationRunId(result.evaluation_run_id);
      await loadEvaluationHistory();
      await loadEvaluationInsights(result.evaluation_run_id);
    } catch (err: any) {
      setEvaluationError(err.message || "Failed to execute evaluation benchmark.");
    } finally {
      setIsRunSubmitting(false);
    }
  };

  const handleTriggerScenario = async (scenarioId: string) => {
    setIsTriggeringScenario(true);
    setActiveResilienceScenario(null);
    setResilienceError(null);
    setFailureScenarioResult("");

    const scenarioMeta = failureScenarios.find((s) => s.scenario_id === scenarioId);

    try {
      const result = await api.triggerFailureScenario(scenarioId);

      if (result.data) {
        setActiveResilienceScenario({
          scenario_id: scenarioId,
          title: scenarioMeta?.title || scenarioId,
          severity: scenarioMeta?.severity || "high",
          ...result.data,
          error_code: result.error?.code,
          error_message: result.error?.message,
        });
      }

      const actualMessage = result.error?.message || "Operation succeeded safely.";
      setFailureScenarioResult(`Scenario ${scenarioId} executed: ${actualMessage}`);
    } catch (err: any) {
      setResilienceError(err.message || "Failed to trigger failure scenario.");
    } finally {
      setIsTriggeringScenario(false);
    }
  };

  const handleExecuteReadiness = async () => {
    setIsReadinessRunning(true);
    try {
      const data = await api.executeReadiness();
      setReadinessValidation(data);
    } catch (err: any) {
      alert(err.message || "Readiness validation failed.");
    } finally {
      setIsReadinessRunning(false);
    }
  };

  const handleSeedDemo = async () => {
    setIsDemoMutating(true);
    setDemoMutationMessage("");
    try {
      await api.seedDemo();
      setDemoMutationMessage("✓ Scenario seeded with multi-archetype failed payments and recovery traces.");
      await loadCommandCenter();
    } catch (err: any) {
      setDemoMutationMessage(`Seeding error: ${err.message}`);
    } finally {
      setIsDemoMutating(false);
    }
  };

  const handleResetDemo = async () => {
    setIsDemoMutating(true);
    setDemoMutationMessage("");
    try {
      await api.resetDemo();
      setDemoMutationMessage("✓ Recovery state reset to initial baseline.");
      await loadCommandCenter();
    } catch (err: any) {
      setDemoMutationMessage(`Reset error: ${err.message}`);
    } finally {
      setIsDemoMutating(false);
    }
  };

  const selectedItem = useMemo(
    () => opportunities.find((item) => item.id === selectedOpportunityId) ?? null,
    [opportunities, selectedOpportunityId]
  );

  return (
    <main className="ui-shell">
      <div className="ui-container">
        {/* Header with operating status chips, theme switcher and demo tour */}
        <Header
          operatingStatus={operatingStatus}
          isLoading={isLoading}
          isDemoMutating={isDemoMutating}
          demoMessage={demoMutationMessage}
          autoRefresh={autoRefreshEnabled}
          onRefresh={loadCommandCenter}
          onSeedDemo={handleSeedDemo}
          onResetDemo={handleResetDemo}
          onToggleAutoRefresh={setAutoRefreshEnabled}
          onOpenDemoTour={() => setIsDemoTourOpen(true)}
          activeTab={activeTab}
        />

        {primaryError && (
          <ErrorBanner
            title="Unable to load recovery telemetry"
            message={primaryError}
            onRetry={loadCommandCenter}
            isRetrying={isLoading}
          />
        )}

        {/* Primary Navigation Tabs */}
        <Navigation
          activeTab={activeTab}
          onSelectTab={handleTabChange}
          openCount={summary?.active_opportunities}
          readinessScore={readinessValidation?.readiness_score}
        />

        {/* MAIN BODY PER ACTIVE TAB */}
        {isLoading && !summary ? (
          <div className="main-loading-state">
            <KpiGridSkeleton />
            <TableSkeleton rows={8} />
          </div>
        ) : (
          <>
            {/* TAB 1: COMMAND CENTER */}
            {activeTab === "Command Center" && summary && (
              <div className="command-center-layout">
                {/* 1. Executive 6-KPI Scorecard Grid */}
                <ExecutiveKpiGrid summary={summary} onNavigateTab={handleNavigateFromKpi} />

                {/* 2. Compact Autonomous Recovery Loop & Executive Briefing */}
                <ExecutiveStoryBanner
                  summary={summary}
                  opportunities={opportunities}
                />

                {/* 3. Executive Decision Insights (What Happened / Why It Matters / What To Do) */}
                <ActionableInsights summary={summary} operatingStatus={operatingStatus} />

                {/* 4. Row 1: Recovery Economics & 7-Day Performance Trend */}
                <div className="command-center-2col-row">
                  <RecoveryImpactChart summary={summary} />
                  <TrendChart
                    data={dashboardTrend}
                    error={trendError}
                    onRetry={() => api.getTrend().then(setDashboardTrend).catch(() => undefined)}
                  />
                </div>

                {/* 5. Row 2: Visual Recovery Funnel & AI Recovery Copilot */}
                <div className="command-center-2col-row">
                  <RecoveryFunnel funnel={summary.funnel} />
                  <CopilotCard
                    copilot={summary.ai_copilot}
                    onSelectOpportunity={(id) => {
                      setSelectedOpportunityId(id);
                    }}
                  />
                </div>

                {/* 6. Row 3: Priority Recovery Queue & Live Activity / Gateway Health */}
                <div className="command-center-2col-row">
                  <PriorityQueue
                    opportunities={opportunities}
                    onSelectOpportunity={(id) => {
                      setSelectedOpportunityId(id);
                    }}
                    onViewAll={() => setActiveTab("Opportunities")}
                  />
                  <div className="activity-health-column">
                    <OperatingHealth healthItems={healthItems} />
                    <EventStream
                      events={dashboardEvents}
                      error={eventsError}
                      onRetry={() => api.getEvents().then(setDashboardEvents).catch(() => undefined)}
                    />
                  </div>
                </div>
              </div>
            )}

            {/* TAB 2: OPPORTUNITIES */}
            {activeTab === "Opportunities" && (
              <div className="opportunities-tab-layout">
                <div className="panel opportunities-header-panel">
                  <div className="panel-header-with-badge">
                    <div>
                      <span className="section-step-tag">OPERATIONAL RECOVERY LEDGER</span>
                      <h2>Revenue Recovery Opportunities</h2>
                      <p className="panel-copy">
                        All failed payment exposure ranked for automated action with deterministic safety policy and outcome context.
                      </p>
                    </div>
                    <span className="badge badge-info badge-sm">Live Ingestion Ledger</span>
                  </div>
                </div>

                {/* Search & Filter Controls */}
                <OpportunityFilters
                  status={statusFilter}
                  action={actionFilter}
                  search={searchFilter}
                  confidenceFilter={confidenceFilter}
                  amountFilter={amountFilter}
                  onFilterChange={(f) => {
                    setOpportunityPage(1);
                    setStatusFilter(f.status);
                    setActionFilter(f.action);
                    setSearchFilter(f.search);
                    if (f.confidenceFilter) setConfidenceFilter(f.confidenceFilter);
                    if (f.amountFilter) setAmountFilter(f.amountFilter);
                  }}
                  onReset={() => {
                    setOpportunityPage(1);
                    setStatusFilter("ALL");
                    setActionFilter("ALL");
                    setSearchFilter("");
                    setConfidenceFilter("ALL");
                    setAmountFilter("ALL");
                  }}
                />

                {opportunitiesError ? (
                  <ErrorBanner
                    title="Opportunities Load Error"
                    message={opportunitiesError}
                    onRetry={() => loadOpportunities(true)}
                  />
                ) : isOpportunityLoading ? (
                  <TableSkeleton rows={8} />
                ) : opportunities.length === 0 ? (
                  <EmptyState
                    title="No recovery opportunities found"
                    description="No failed transactions match your current search and filters. Click below to populate the multi-archetype recovery scenario."
                    actionLabel="Seed Recovery Scenario"
                    onAction={handleSeedDemo}
                    isLoadingAction={isDemoMutating}
                    icon="🎯"
                  />
                ) : (
                  <OpportunityTable
                    items={opportunities}
                    selectedId={selectedOpportunityId}
                    onSelect={(id) => setSelectedOpportunityId(id)}
                    page={opportunityPage}
                    pageSize={opportunityPageSize}
                    totalCount={opportunityTotalCount}
                    totalPages={opportunityTotalPages}
                    hasNext={opportunityHasNext}
                    hasPrev={opportunityHasPrev}
                    onPageChange={setOpportunityPage}
                    onPageSizeChange={(newSize) => {
                      setOpportunityPage(1);
                      setOpportunityPageSize(newSize);
                    }}
                    confidenceFilter={confidenceFilter}
                    amountFilter={amountFilter}
                  />
                )}
              </div>
            )}

            {/* TAB 3: EVALUATION */}
            {activeTab === "Evaluation" && (
              <div className="evaluation-tab-layout">
                <div className="panel evaluation-header-panel">
                  <div className="panel-header-with-badge">
                    <div>
                      <h2>Model Benchmark & Comparative Evaluation</h2>
                      <p className="panel-copy">
                        Statistical validation of RecoverIQ machine learning classification against naive payment retry baselines.
                      </p>
                    </div>
                    <span className="badge badge-info badge-sm">Holdout Test Split</span>
                  </div>

                  {/* Benchmark Run Form */}
                  <EvaluationRunForm isSubmitting={isRunSubmitting} onSubmit={handleRunEvaluation} />
                </div>

                {evaluationError && (
                  <ErrorBanner
                    title="Evaluation Data Error"
                    message={evaluationError}
                    onRetry={() => selectedEvaluationRunId && loadEvaluationInsights(selectedEvaluationRunId)}
                  />
                )}

                <div className="evaluation-split-grid">
                  {/* Left: Run History List */}
                  <div className="panel eval-history-column">
                    <h3>Benchmark Runs</h3>
                    <div className="eval-run-list">
                      {evaluationHistory.map((item) => (
                        <button
                          key={item.evaluation_run_id}
                          className={`eval-run-item ${selectedEvaluationRunId === item.evaluation_run_id ? "active" : ""}`}
                          onClick={() => {
                            setSelectedEvaluationRunId(item.evaluation_run_id);
                            loadEvaluationInsights(item.evaluation_run_id);
                          }}
                        >
                          <div className="run-item-top">
                            <span className="run-id font-mono">{item.evaluation_run_id}</span>
                            <span className="badge badge-good badge-sm">F1: {(item.f1 * 100).toFixed(1)}%</span>
                          </div>
                          <div className="run-item-meta">
                            <span>{item.records} records</span>
                            <span>{item.last_created_at ? new Date(item.last_created_at).toLocaleDateString() : ""}</span>
                          </div>
                        </button>
                      ))}
                    </div>
                  </div>

                  {/* Right: Comparative Results */}
                  <div className="eval-results-column">
                    {isEvaluationLoading ? (
                      <div className="panel p-xxl text-center">
                        <p className="helper-message">Loading statistical benchmark insights...</p>
                      </div>
                    ) : evaluationComparison ? (
                      <>
                        <EvaluationHero
                          comparison={evaluationComparison}
                          totalRuns={evaluationHistory.length}
                        />
                        <ExecutiveMetricsCards
                          comparison={evaluationComparison}
                          drilldown={evaluationDrilldown}
                        />
                        <ComparisonMatrix comparison={evaluationComparison} />
                        {evaluationDrilldown && <ConfusionMatrix drilldown={evaluationDrilldown} />}
                        {evaluationDrilldown && <SampleTestCasesTable drilldown={evaluationDrilldown} />}
                        <ReproducibilityCard comparison={evaluationComparison} />
                      </>
                    ) : (
                      <div className="panel p-xxl text-center">
                        <p className="helper-message">Select an evaluation benchmark from the left to inspect metrics.</p>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            )}

            {/* TAB 4: RELIABILITY & SECURITY */}
            {activeTab === "Reliability & Security" && (
              <div className="reliability-tab-layout">
                <ReliabilityHero operatingStatus={operatingStatus} />
                <OperatingHealthCards operatingStatus={operatingStatus} />
                <FailureScenariosSection
                  scenarios={failureScenarios}
                  activeScenario={activeResilienceScenario}
                  statusResult={failureScenarioResult}
                  error={resilienceError}
                  onTriggerScenario={handleTriggerScenario}
                  isTriggering={isTriggeringScenario}
                />
                <SecurityControlsMatrix />
                <TechnicalIntegrationDetails events={dashboardEvents} />
              </div>
            )}

            {/* TAB 5: PRODUCTION READINESS */}
            {activeTab === "Production Readiness" && (
              <div className="readiness-tab-layout">
                <div className="panel">
                  <div className="panel-header-with-badge">
                    <div>
                      <span className="section-step-tag">GO/NO-GO DECISION GATE</span>
                      <h2>Production Readiness & Release Validation</h2>
                      <p className="panel-copy">
                        Continuous release gate evaluating security, database integrity, failover resilience, and cryptographic auditability.
                      </p>
                    </div>
                    <span className="badge badge-info badge-sm">Release Gate Engine</span>
                  </div>
                </div>

                {readinessValidation ? (
                  <div className="readiness-content-area">
                    <ReadinessHero
                      data={readinessValidation}
                      isRunning={isReadinessRunning}
                      onExecuteValidation={handleExecuteReadiness}
                    />
                    <RemediationBanner recommendation={readinessValidation.recommended_next_step} />
                    <ReadinessCheckGrid checks={readinessValidation.checks} />
                  </div>
                ) : (
                  <div className="readiness-unexecuted-box">
                    <div className="readiness-unexecuted-icon">🚀</div>
                    <h3>Readiness Validation Suite Unexecuted</h3>
                    <p>
                      Execute the live end-to-end security, database connectivity, AI fallback, and idempotency release audit.
                    </p>
                    <button
                      onClick={handleExecuteReadiness}
                      disabled={isReadinessRunning}
                      className="btn btn-primary mt-lg"
                    >
                      {isReadinessRunning ? "Running Audits..." : "Execute Readiness Validation"}
                    </button>
                  </div>
                )}
              </div>
            )}
          </>
        )}

        {/* Opportunity Detail Slide-over Drawer */}
        <OpportunityDrawer
          isOpen={selectedOpportunityId !== null}
          onClose={() => setSelectedOpportunityId(null)}
          selectedItem={selectedItem}
          detail={detail}
          isLoading={isDetailLoading}
          isExecuting={isExecutingRecovery}
          executionMessage={executionMessage}
          onExecuteRecovery={handleExecuteRecovery}
        />

        {/* Post-Recovery Success Confirmation Modal */}
        <RecoverySuccessModal
          isOpen={successModalData.isOpen}
          opportunity={successModalData.opportunity}
          detail={successModalData.detail}
          onClose={() => setSuccessModalData({ isOpen: false, opportunity: null, detail: null })}
        />

        {/* 2-Minute Interactive Guided Tour Modal */}
        <GuidedDemoModal
          isOpen={isDemoTourOpen}
          onClose={() => setIsDemoTourOpen(false)}
          onNavigateTab={handleTabChange}
          onSelectTopOpportunity={() => {
            if (opportunities.length > 0) {
              setSelectedOpportunityId(opportunities[0].id);
            }
          }}
        />
      </div>
    </main>
  );
}
