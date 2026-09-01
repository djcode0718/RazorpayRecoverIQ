import { OpportunityListItem } from "../../types";
import { formatMinorCurrency, formatPercentage } from "../../utils/formatters";
import { Badge } from "../common/Badge";

type QueuePreviewProps = {
  opportunities: OpportunityListItem[];
  onSelectOpportunity: (id: number) => void;
  onViewAll: () => void;
};

export function QueuePreview({ opportunities, onSelectOpportunity, onViewAll }: QueuePreviewProps) {
  const openItems = opportunities
    .filter((o) => o.status !== "CLOSED" && o.status !== "RESOLVED")
    .slice(0, 5);

  return (
    <div className="panel queue-panel">
      <div className="panel-header-with-action">
        <div>
          <h2>Live Prioritized Recovery Queue</h2>
          <p className="panel-copy">Top actionable recovery opportunities ranked by expected net yield.</p>
        </div>
        <button onClick={onViewAll} className="btn btn-tertiary btn-sm">
          View All &rarr;
        </button>
      </div>

      {openItems.length === 0 ? (
        <div className="empty-state-mini">
          <p>No active opportunities in queue.</p>
        </div>
      ) : (
        <div className="table-responsive">
          <table className="fintech-table compact-table">
            <thead>
              <tr>
                <th>Opportunity</th>
                <th>Failure Category</th>
                <th className="numeric">Revenue at Risk</th>
                <th>Recommended Action</th>
                <th>Confidence</th>
                <th className="numeric">Expected Recovery</th>
                <th>Policy Gate</th>
              </tr>
            </thead>
            <tbody>
              {openItems.map((opp) => (
                <tr
                  key={opp.id}
                  onClick={() => onSelectOpportunity(opp.id)}
                  className="clickable-row"
                  tabIndex={0}
                  role="button"
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      onSelectOpportunity(opp.id);
                    }
                  }}
                >
                  <td>
                    <strong className="opp-primary">#{opp.id}</strong>
                    <span className="opp-secondary">{opp.customer_reference || "Direct Customer"}</span>
                  </td>
                  <td>
                    <span className="opp-primary">{opp.failure_category || "Network"}</span>
                    <span className="opp-secondary">{opp.failure_reason || "Gateway Timeout"}</span>
                  </td>
                  <td className="numeric">
                    <strong className="amount-hero">{formatMinorCurrency(opp.amount_at_risk_minor)}</strong>
                  </td>
                  <td>
                    <Badge text={opp.recommended_action || "RETRY"} tone="info" size="sm" />
                  </td>
                  <td>
                    <div className="confidence-pill-inline">
                      <span>{formatPercentage(opp.confidence, false)}</span>
                    </div>
                  </td>
                  <td className="numeric">
                    <strong className="text-good">
                      {formatMinorCurrency(opp.expected_recovery_minor)}
                    </strong>
                  </td>
                  <td>
                    <Badge
                      text={opp.policy_result || "ALLOW"}
                      tone={opp.policy_result === "ALLOW" ? "good" : "bad"}
                      size="sm"
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
