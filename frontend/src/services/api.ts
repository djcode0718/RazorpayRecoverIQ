import {
  SummaryResponse,
  TrendDataPoint,
  DashboardEvent,
  OpportunityListResponse,
  OpportunityDetailResponse,
  RazorpayStatusResponse,
  EvaluationHistoryResponse,
  EvaluationComparisonResponse,
  EvaluationDrilldownResponse,
  EvaluationRunResponse,
  FailureScenariosResponse,
  ReadinessValidationData,
} from "../types";

async function safeFetch(url: string, init?: RequestInit): Promise<Response> {
  try {
    return await fetch(url, init);
  } catch (err) {
    throw new Error("Unable to reach the RecoverIQ API. Check network and backend connection.");
  }
}

async function checkResponseError(response: Response, defaultMessage: string): Promise<void> {
  if (response.status === 401 || response.status === 403) {
    throw new Error("Access denied.");
  }
  if (response.status === 422) {
    throw new Error("Validation failed for requested data.");
  }
  if (response.status === 503) {
    throw new Error("Recovery service is temporarily unavailable.");
  }
  if (response.status >= 500) {
    throw new Error("RecoverIQ API returned an unexpected error.");
  }
  if (!response.ok) {
    let msg = defaultMessage;
    try {
      const payload = await response.json();
      if (payload?.error?.message) {
        msg = payload.error.message;
      }
    } catch (_) {}
    throw new Error(msg);
  }
}

export const api = {
  async getSummary() {
    const response = await safeFetch("/api/v1/dashboard/summary");
    await checkResponseError(response, "Unable to load dashboard summary.");
    const payload = (await response.json()) as SummaryResponse;
    if (!payload.success || !payload.data) {
      throw new Error(payload.error?.message || "Unable to load dashboard summary.");
    }
    return payload.data;
  },

  async getTrend() {
    const response = await safeFetch("/api/v1/dashboard/trend");
    await checkResponseError(response, "Unable to load dashboard trend.");
    const payload = (await response.json()) as { success: boolean; data?: TrendDataPoint[]; error?: { message?: string } };
    if (!payload.success || !payload.data) {
      throw new Error(payload.error?.message || "Unable to load dashboard trend.");
    }
    return payload.data;
  },

  async getEvents() {
    const response = await safeFetch("/api/v1/dashboard/events");
    await checkResponseError(response, "Unable to load dashboard events.");
    const payload = (await response.json()) as { success: boolean; data?: DashboardEvent[]; error?: { message?: string } };
    if (!payload.success || !payload.data) {
      throw new Error(payload.error?.message || "Unable to load dashboard events.");
    }
    return payload.data;
  },

  async getRazorpayStatus() {
    const response = await safeFetch("/api/v1/integrations/razorpay/status");
    await checkResponseError(response, "Unable to load Razorpay integration status.");
    const payload = (await response.json()) as RazorpayStatusResponse;
    if (!payload.success || !payload.data) {
      throw new Error(payload.error?.message || "Unable to load Razorpay integration status.");
    }
    return payload.data;
  },

  async getOpportunities(params: {
    page: number;
    pageSize: number;
    status?: string;
    action?: string;
    search?: string;
    sortBy?: string;
  }) {
    const query = new URLSearchParams();
    query.set("pagination_mode", "page");
    query.set("page", String(params.page));
    query.set("page_size", String(params.pageSize));
    query.set("sort_by", params.sortBy || "updated_desc");
    if (params.status && params.status !== "ALL") {
      query.set("status", params.status);
    }
    if (params.action && params.action !== "ALL") {
      query.set("action", params.action);
    }
    if (params.search && params.search.trim().length > 0) {
      query.set("search", params.search.trim());
    }

    const response = await safeFetch(`/api/v1/opportunities?${query.toString()}`);
    await checkResponseError(response, "Unable to load opportunities.");
    const payload = (await response.json()) as OpportunityListResponse;
    if (!payload.success || !payload.data) {
      throw new Error(payload.error?.message || "Unable to load opportunities.");
    }
    return payload.data;
  },

  async getOpportunityDetail(id: number) {
    const response = await safeFetch(`/api/v1/opportunities/${id}`);
    await checkResponseError(response, `Unable to load opportunity #${id} detail.`);
    const payload = (await response.json()) as OpportunityDetailResponse;
    if (!payload.success || !payload.data) {
      throw new Error(payload.error?.message || "Unable to load opportunity detail.");
    }
    return payload.data;
  },

  async executeRecovery(id: number) {
    const response = await safeFetch(`/api/v1/opportunities/${id}/execute`, { method: "POST" });
    const payload = await response.json();
    if (!response.ok || !payload.success) {
      throw new Error(payload.error?.message || "Recovery execution failed.");
    }
    return payload;
  },

  async getEvaluationHistory(limit = 10) {
    const response = await safeFetch(`/api/v1/evaluation/history?limit=${limit}`);
    await checkResponseError(response, "Unable to load evaluation history.");
    const payload = (await response.json()) as EvaluationHistoryResponse;
    if (!payload.success || !payload.data) {
      throw new Error(payload.error?.message || "Unable to load evaluation history.");
    }
    return payload.data.items;
  },

  async getEvaluationInsights(runId: string) {
    const [comparisonResponse, drilldownResponse] = await Promise.all([
      safeFetch(`/api/v1/evaluation/${runId}/comparison`),
      safeFetch(`/api/v1/evaluation/${runId}/drilldown`),
    ]);

    await checkResponseError(comparisonResponse, "Unable to load evaluation comparison.");
    await checkResponseError(drilldownResponse, "Unable to load evaluation drilldown.");

    const comparisonPayload = (await comparisonResponse.json()) as EvaluationComparisonResponse;
    const drilldownPayload = (await drilldownResponse.json()) as EvaluationDrilldownResponse;

    if (!comparisonPayload.success || !comparisonPayload.data) {
      throw new Error(comparisonPayload.error?.message || "Unable to load evaluation comparison.");
    }
    if (!drilldownPayload.success || !drilldownPayload.data) {
      throw new Error(drilldownPayload.error?.message || "Unable to load evaluation drilldown.");
    }

    return {
      comparison: comparisonPayload.data,
      drilldown: drilldownPayload.data,
    };
  },

  async runEvaluation(params: {
    dataset_version: string;
    split: string;
    generation_seed: number;
    total_cases: number;
  }) {
    const response = await safeFetch("/api/v1/evaluation/run", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ ...params, generate_if_missing: true }),
    });
    await checkResponseError(response, "Unable to run evaluation.");
    const payload = (await response.json()) as EvaluationRunResponse;
    if (!payload.success || !payload.data) {
      throw new Error(payload.error?.message || "Unable to run evaluation.");
    }
    return payload.data;
  },

  async getFailureScenarios() {
    const response = await safeFetch("/api/v1/failure-demos");
    await checkResponseError(response, "Unable to load failure scenarios.");
    const payload = (await response.json()) as FailureScenariosResponse;
    if (!payload.success || !payload.data) {
      throw new Error(payload.error?.message || "Unable to load failure scenarios.");
    }
    return payload.data.scenarios;
  },

  async triggerFailureScenario(scenarioId: string) {
    const response = await safeFetch("/api/v1/failure-demos/trigger", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ scenario_id: scenarioId }),
    });
    const payload = await response.json();
    return {
      status: response.status,
      ok: response.ok,
      data: payload.data,
      error: payload.error,
    };
  },

  async executeReadiness(): Promise<ReadinessValidationData> {
    const response = await safeFetch("/api/v1/readiness/execute", { method: "POST" });
    const payload = await response.json();
    if (!response.ok || !payload.success || !payload.data) {
      throw new Error(payload.error?.message || "Unable to execute readiness audit.");
    }
    return payload.data;
  },

  async seedDemo() {
    const response = await safeFetch("/api/v1/demo/seed-core-recovery", { method: "POST" });
    const payload = await response.json();
    if (!response.ok || !payload.success) {
      throw new Error(payload.error?.message || "Demo seeding failed.");
    }
    return payload;
  },

  async resetDemo() {
    const response = await safeFetch("/api/v1/demo/reset-core-recovery", { method: "POST" });
    const payload = await response.json();
    if (!response.ok || !payload.success) {
      throw new Error(payload.error?.message || "Demo reset failed.");
    }
    return payload;
  },
};
