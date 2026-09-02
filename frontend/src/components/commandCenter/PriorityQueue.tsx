import { OpportunityListItem } from "../../types";
import { rankOpportunities } from "../../utils/calculations";
import { formatMinorCurrency, formatPercentage } from "../../utils/formatters";
import { Badge } from "../common/Badge";

type PriorityQueueProps = {
  opportunities: OpportunityListItem[];
  onSelectOpportunity: (id: number) => void;
  onViewAll: () => void;
};

function formatActionShort(action?: string | null): string {
  if (!action) return "Smart Link";
  switch (action.toUpperCase()) {
    case "SMART_PAYMENT_LINK":
      return "Payment Link";
    case "RETRY_AFTER_COOLDOWN":
      return "Auto Retry";
    case "ESCALATE_TO_MANUAL":
      return "Manual Review";
    case "BLOCK_AND_FLAG":
      return "Safety Block";
    default:
      return action.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
  }
}

export function PriorityQueue({ opportunities, onSelectOpportunity, onViewAll }: PriorityQueueProps) {
  const ranked = rankOpportunities(
    opportunities.filter((o) => o.status !== "CLOSED" && o.status !== "RESOLVED")
  ).slice(0, 4);

  return (
    <div className="panel priority-queue-panel">
      <div className="panel-header-with-action">
        <div>
          <div className="queue-title-row">
            <h2>Priority Recovery Queue</h2>
            <span className="badge badge-info badge-sm">Multi-Factor Ranked</span>
          </div>
          <p className="panel-copy">
            Opportunities prioritized by expected recovery yield, customer intent score, and safety policy clearance.
          </p>
        </div>
        <button onClick={onViewAll} className="btn btn-tertiary btn-sm">
          All Opportunities &rarr;
        </button>
      </div>

      {ranked.length === 0 ? (
        <div className="empty-state-mini">
          <p>No open opportunities in queue.</p>
        </div>
      ) : (
        <div className="priority-queue-list">
          {ranked.map((item) => (
            <div
              key={item.id}
              className="priority-card-item"
              onClick={() => onSelectOpportunity(item.id)}
              tabIndex={0}
              role="button"
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  onSelectOpportunity(item.id);
                }
              }}
            >
              <div className="priority-rank-badge">
                <span className="rank-hash">#</span>
                <span className="rank-num">{item.priorityRank}</span>
              </div>

              <div className="priority-main-info">
                <div className="priority-head-row">
                  <div className="priority-id-block">
                    <strong className="priority-opp-id">#OPP-{item.id}</strong>
                    <span className="priority-cust-ref">{item.customer_reference}</span>
                  </div>
                  <div className="priority-tags">
                    <Badge
                      text={item.urgencyLevel === "HIGH" ? "⚡ Urgent" : "Standard"}
                      tone={item.urgencyLevel === "HIGH" ? "warn" : "neutral"}
                      size="sm"
                    />
                    <Badge
                      text={`${item.priorityScore} Pts`}
                      tone={item.priorityScore >= 80 ? "good" : "info"}
                      size="sm"
                    />
                  </div>
                </div>

                <div className="priority-metrics-row">
                  <span className="metric-pill">
                    Exposure: <strong>{formatMinorCurrency(item.amount_at_risk_minor)}</strong>
                  </span>
                  <span className="metric-pill">
                    Expected: <strong className="text-good">{formatMinorCurrency(item.expected_recovery_minor)}</strong>
                  </span>
                  <span className="metric-pill">
                    Confidence: <strong>{formatPercentage(item.confidence, false)}</strong>
                  </span>
                  <span className="metric-pill action-pill">
                    Action: <strong className="text-primary">{formatActionShort(item.recommended_action)}</strong>
                  </span>
                </div>

                <div className="priority-rationale-box">
                  <span className="rationale-summary">
                    <strong>Ranking Rationale:</strong> {item.priorityReasons[0] || "High financial exposure with verified customer retry intent."}
                  </span>
                </div>
              </div>

              <div className="priority-action-col">
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    onSelectOpportunity(item.id);
                  }}
                  className="btn btn-primary btn-sm"
                  title="Open full opportunity evidence drawer"
                >
                  Inspect &rarr;
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
