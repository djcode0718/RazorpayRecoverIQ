import { useState } from "react";
import { OpportunityListItem } from "../../types";
import { formatMinorCurrency, formatPercentage } from "../../utils/formatters";
import { Badge } from "../common/Badge";

type ActionCenterProps = {
  opportunities: OpportunityListItem[];
  onSelectOpportunity: (id: number) => void;
  onExecuteRecovery: (id: number) => void;
};

export function ActionCenter({
  opportunities,
  onSelectOpportunity,
  onExecuteRecovery,
}: ActionCenterProps) {
  const [activeBucket, setActiveBucket] = useState<"READY" | "ATTENTION" | "PENDING" | "RECOVERED">("READY");

  const readyToRecover = opportunities.filter(
    (o) => o.status === "OPEN" && o.policy_result === "ALLOW" && o.execution_status === "NOT_EXECUTED"
  );

  const needsAttention = opportunities.filter(
    (o) => o.status === "OPEN" && (o.policy_result !== "ALLOW" || o.risk_bucket?.includes("HIGH") || o.recommended_action === "ESCALATE")
  );

  const awaitingVerification = opportunities.filter(
    (o) => o.status === "OPEN" && (o.execution_status === "RUNNING" || o.execution_status === "SUCCEEDED" || o.verification_status === "PENDING")
  );

  const recentlyRecovered = opportunities.filter(
    (o) => o.status === "RESOLVED" || o.outcome === "RECOVERED"
  );

  const currentItems =
    activeBucket === "READY"
      ? readyToRecover
      : activeBucket === "ATTENTION"
      ? needsAttention
      : activeBucket === "PENDING"
      ? awaitingVerification
      : recentlyRecovered;

  return (
    <div className="panel action-center-panel">
      <div className="panel-header-with-badge">
        <div>
          <h2>Operational Action Center</h2>
          <p className="panel-copy">
            Categorized workflow queues for immediate decision-making and human-in-the-loop oversight.
          </p>
        </div>
        <span className="badge badge-info badge-sm">Autonomous Workflow Engine</span>
      </div>

      {/* Action Center Tabs */}
      <div className="action-center-tabs">
        <button
          className={`action-tab-btn ${activeBucket === "READY" ? "active" : ""}`}
          onClick={() => setActiveBucket("READY")}
        >
          <span className="action-tab-title">Ready to Recover</span>
          <span className="action-tab-badge badge-good">{readyToRecover.length}</span>
        </button>
        <button
          className={`action-tab-btn ${activeBucket === "ATTENTION" ? "active" : ""}`}
          onClick={() => setActiveBucket("ATTENTION")}
        >
          <span className="action-tab-title">Needs Attention</span>
          <span className="action-tab-badge badge-warn">{needsAttention.length}</span>
        </button>
        <button
          className={`action-tab-btn ${activeBucket === "PENDING" ? "active" : ""}`}
          onClick={() => setActiveBucket("PENDING")}
        >
          <span className="action-tab-title">Awaiting Verification</span>
          <span className="action-tab-badge badge-info">{awaitingVerification.length}</span>
        </button>
        <button
          className={`action-tab-btn ${activeBucket === "RECOVERED" ? "active" : ""}`}
          onClick={() => setActiveBucket("RECOVERED")}
        >
          <span className="action-tab-title">Recently Recovered</span>
          <span className="action-tab-badge badge-neutral">{recentlyRecovered.length}</span>
        </button>
      </div>

      {/* Action Item Cards */}
      <div className="action-items-list">
        {currentItems.length === 0 ? (
          <div className="empty-state-mini">
            <p>No opportunities in this queue right now.</p>
          </div>
        ) : (
          currentItems.slice(0, 4).map((item) => (
            <div key={item.id} className="action-card-item">
              <div className="action-card-left">
                <div className="action-card-id-row">
                  <strong className="action-opp-id">#OPP-{item.id}</strong>
                  <span className="action-cust-ref">{item.customer_reference}</span>
                  <Badge text={item.failure_category || "Network"} tone="neutral" size="sm" />
                </div>
                <div className="action-card-financials">
                  <span>
                    Exposure: <strong>{formatMinorCurrency(item.amount_at_risk_minor)}</strong>
                  </span>
                  <span>&bull;</span>
                  <span>
                    Expected: <strong className="text-good">{formatMinorCurrency(item.expected_recovery_minor)}</strong>
                  </span>
                  <span>&bull;</span>
                  <span>
                    Confidence: <strong>{formatPercentage(item.confidence, false)}</strong>
                  </span>
                </div>
              </div>

              <div className="action-card-right">
                <button
                  onClick={() => onSelectOpportunity(item.id)}
                  className="btn btn-tertiary btn-sm"
                >
                  Review Evidence
                </button>
                {item.policy_result === "ALLOW" && item.status === "OPEN" && item.execution_status === "NOT_EXECUTED" && (
                  <button
                    onClick={() => onExecuteRecovery(item.id)}
                    className="btn btn-primary btn-sm"
                  >
                    Request Payment
                  </button>
                )}
                {item.status === "RESOLVED" && (
                  <Badge text="✓ RECOVERED" tone="good" size="sm" />
                )}
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
